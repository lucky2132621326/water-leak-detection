"""CP-SAT Work Order Scheduler

Assigns leak repairs to field crews using Google OR-Tools CP-SAT.

This previously did `crews[idx % len(crews)]` — round-robin with a hardcoded
start time — while calling itself a CP-SAT scheduler. It now actually solves a
constraint model:

  Decision      which crew repairs which leak, and in what order on that crew
  Constraints   a crew does one job at a time; jobs only go to crews holding
                the required skill; every leak is assigned exactly once
  Objective     minimise total weighted completion time, weighted by leak
                severity — so a 2.5 L/min rupture is scheduled ahead of a
                0.3 L/min seep even if the seep was reported first

If OR-Tools is unavailable or the model proves infeasible, the scheduler falls
back to a severity-ordered greedy assignment and says so in `solver_status`,
rather than silently returning something that looks optimal.
"""
import time

from backend.utils.logger import logger

try:
    from ortools.sat.python import cp_model
    _HAS_ORTOOLS = True
except ImportError:  # pragma: no cover - exercised only on installs without OR-Tools
    _HAS_ORTOOLS = False

# Travel/setup overhead charged when a crew is dispatched to a zone it is not
# already stationed in. Coarse by design — the rig has no real geography.
_TRAVEL_PENALTY_MIN = 20

_ZONE_OF_NODE = {
    "Branch_A": "Zone_1",
    "Branch_B": "Zone_2",
    "Main_Trunk": "Zone_3",
}

# Which crew skill a leak location demands.
_SKILL_FOR_NODE = {
    "Branch_A": "BRANCH_A_REPAIR",
    "Branch_B": "BRANCH_B_REPAIR",
    "Main_Trunk": "TRUNK_PIPE_REPAIR",
}


class CPSatWorkOrderScheduler:
    def __init__(self, crews=None, horizon_minutes: int = 24 * 60):
        self.crews = crews or [
            {"id": "CREW_ALPHA", "skills": ["BRANCH_A_REPAIR", "HYDRAULIC"], "location": "Zone_1", "status": "AVAILABLE"},
            {"id": "CREW_BETA", "skills": ["BRANCH_B_REPAIR", "FLOW_DIAGNOSTICS"], "location": "Zone_2", "status": "AVAILABLE"},
            {"id": "CREW_GAMMA", "skills": ["TRUNK_PIPE_REPAIR", "HEAVY_REPAIR"], "location": "Zone_3", "status": "AVAILABLE"},
        ]
        self.horizon = horizon_minutes

    # --- helpers ----------------------------------------------------------
    @staticmethod
    def _duration_minutes(severity_lpm: float) -> int:
        """Bigger leaks take longer to repair. Minutes, integral for CP-SAT."""
        return max(30, int(round(60 + severity_lpm * 48)))

    @staticmethod
    def _priority(severity_lpm: float) -> str:
        if severity_lpm >= 1.5:
            return "URGENT"
        if severity_lpm >= 0.5:
            return "HIGH"
        return "NORMAL"

    def _eligible(self, crew: dict, node: str) -> bool:
        if crew.get("status") != "AVAILABLE":
            return False
        required = _SKILL_FOR_NODE.get(node)
        # An unmapped location is treated as general work any crew can take,
        # rather than silently excluding every crew and forcing infeasibility.
        return required is None or required in crew.get("skills", [])

    def _travel(self, crew: dict, node: str) -> int:
        return 0 if crew.get("location") == _ZONE_OF_NODE.get(node) else _TRAVEL_PENALTY_MIN

    # --- scheduling -------------------------------------------------------
    def optimize_schedule(self, active_leaks, start_epoch: float = None):
        if not active_leaks:
            return []
        start_epoch = start_epoch or time.time()

        if _HAS_ORTOOLS:
            solved = self._solve_cp_sat(active_leaks, start_epoch)
            if solved is not None:
                return solved
            logger.warning("[Scheduler] CP-SAT found no feasible assignment; using severity-ordered fallback")
        else:
            logger.warning("[Scheduler] OR-Tools not installed; using severity-ordered fallback")

        return self._greedy(active_leaks, start_epoch)

    def _solve_cp_sat(self, leaks, start_epoch):
        model = cp_model.CpModel()
        n_leaks, n_crews = len(leaks), len(self.crews)

        durations, severities, nodes = [], [], []
        for leak in leaks:
            sev = float(leak.get("severity_lpm", 1.0))
            severities.append(sev)
            nodes.append(leak.get("location_node", "Branch_A"))
            durations.append(self._duration_minutes(sev))

        # assign[i][c] — leak i handled by crew c
        assign = [[model.NewBoolVar(f"a_{i}_{c}") for c in range(n_crews)] for i in range(n_leaks)]
        starts, ends, sizes = [], [], []

        for i in range(n_leaks):
            eligible = [c for c in range(n_crews) if self._eligible(self.crews[c], nodes[i])]
            if not eligible:
                return None  # no crew can service this leak — infeasible by construction
            model.AddExactlyOne(assign[i][c] for c in eligible)
            for c in range(n_crews):
                if c not in eligible:
                    model.Add(assign[i][c] == 0)

            # Travel depends on which crew takes it, so the effective duration
            # is chosen alongside the assignment.
            travel = model.NewIntVar(0, _TRAVEL_PENALTY_MIN, f"travel_{i}")
            for c in eligible:
                model.Add(travel == self._travel(self.crews[c], nodes[i])).OnlyEnforceIf(assign[i][c])

            s = model.NewIntVar(0, self.horizon, f"s_{i}")
            e = model.NewIntVar(0, self.horizon, f"e_{i}")
            # Occupied time is repair plus travel. This must be a variable, not
            # a constant: pinning the interval size to duration+MAX_TRAVEL while
            # `e` is only duration+travel makes the model infeasible whenever a
            # crew is already in-zone (travel == 0).
            size = model.NewIntVar(durations[i], durations[i] + _TRAVEL_PENALTY_MIN, f"size_{i}")
            model.Add(size == durations[i] + travel)
            model.Add(e == s + size)
            starts.append(s)
            ends.append(e)
            sizes.append(size)

        # A crew does one job at a time.
        for c in range(n_crews):
            crew_intervals = []
            for i in range(n_leaks):
                crew_intervals.append(model.NewOptionalIntervalVar(
                    starts[i], sizes[i], ends[i], assign[i][c], f"iv_{i}_{c}"))
            model.AddNoOverlap(crew_intervals)

        # Weighted completion time — severity is the weight, so urgent leaks
        # are pulled earlier in the schedule.
        weights = [max(1, int(round(sev * 10))) for sev in severities]
        model.Minimize(sum(w * e for w, e in zip(weights, ends)))

        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        solver.parameters.num_search_workers = 4
        status = solver.Solve(model)

        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return None

        status_name = "OPTIMAL" if status == cp_model.OPTIMAL else "FEASIBLE"
        logger.info(f"[Scheduler] CP-SAT {status_name} for {n_leaks} leak(s) across {n_crews} crew(s)")

        orders = []
        for i, leak in enumerate(leaks):
            crew_idx = next(c for c in range(n_crews) if solver.Value(assign[i][c]))
            offset_min = solver.Value(starts[i])
            orders.append(self._work_order(
                idx=i, leak=leak, crew=self.crews[crew_idx],
                severity=severities[i], node=nodes[i],
                duration_min=durations[i], start_epoch=start_epoch, offset_min=offset_min,
                solver_status=f"CP-SAT {status_name}",
            ))
        orders.sort(key=lambda w: w["scheduled_start_ts"])
        return orders

    def _greedy(self, leaks, start_epoch):
        """Severity-first fallback. Honest about what it is."""
        ordered = sorted(enumerate(leaks), key=lambda p: -float(p[1].get("severity_lpm", 1.0)))
        next_free = {crew["id"]: 0 for crew in self.crews}
        orders = []

        for i, leak in ordered:
            sev = float(leak.get("severity_lpm", 1.0))
            node = leak.get("location_node", "Branch_A")
            eligible = [c for c in self.crews if self._eligible(c, node)] or self.crews
            crew = min(eligible, key=lambda c: next_free[c["id"]])
            duration = self._duration_minutes(sev)
            offset = next_free[crew["id"]] + self._travel(crew, node)
            next_free[crew["id"]] = offset + duration
            orders.append(self._work_order(
                idx=i, leak=leak, crew=crew, severity=sev, node=node,
                duration_min=duration, start_epoch=start_epoch, offset_min=offset,
                solver_status="GREEDY FALLBACK",
            ))
        orders.sort(key=lambda w: w["scheduled_start_ts"])
        return orders

    def _work_order(self, idx, leak, crew, severity, node, duration_min, start_epoch, offset_min, solver_status):
        scheduled_ts = start_epoch + offset_min * 60
        return {
            "work_order_id": f"WO-{time.strftime('%Y%m%d', time.localtime(start_epoch))}-{idx + 1:03d}",
            "leak_id": leak.get("id", idx + 1),
            "location_node": node,
            "severity_lpm": round(severity, 3),
            "priority": self._priority(severity),
            "assigned_crew": crew["id"],
            "crew_skills": crew.get("skills", []),
            "estimated_repair_hrs": round(duration_min / 60.0, 2),
            "scheduled_start_ts": scheduled_ts,
            "scheduled_start": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(scheduled_ts)),
            "queue_offset_min": offset_min,
            "solver_status": solver_status,
            "status": "DISPATCHED",
        }
