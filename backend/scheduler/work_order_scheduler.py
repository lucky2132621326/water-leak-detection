"""Work Order Scheduler

Deterministic round-robin crew assignment by leak severity. This is NOT a
CP-SAT/OR-Tools constraint solve — no skill matching, travel-time, or
availability optimization actually happens; crews are picked by
`index % crew_count`. Renamed from the previous `CPSatWorkOrderScheduler` /
`cp_sat_scheduler.py`, which claimed constraint-solving it didn't do.
Replace this with a real solver (or at least real skill/availability
filtering) before presenting the "optimized" framing anywhere user-facing.
"""
import time


class WorkOrderScheduler:
    def __init__(self):
        self.crews = [
            {"id": "CREW_ALPHA", "skills": ["PIPE_SOLENOID", "HYDRAULIC"], "location": "Zone_1", "status": "AVAILABLE"},
            {"id": "CREW_BETA", "skills": ["MICRO_LEAK", "PRESSURE_SEAL"], "location": "Zone_2", "status": "AVAILABLE"},
            {"id": "CREW_GAMMA", "skills": ["MAIN_TRUNK", "HEAVY_REPAIR"], "location": "Zone_3", "status": "AVAILABLE"}
        ]

    def optimize_schedule(self, active_leaks):
        work_orders = []
        now = time.strftime("%Y-%m-%d %H:%M:%S")
        for idx, leak in enumerate(active_leaks):
            severity = leak.get("severity_lpm", 1.0)
            node = leak.get("location_node", "Branch_A")
            priority = "URGENT" if severity > 1.5 else "HIGH"
            assigned_crew = self.crews[idx % len(self.crews)]

            work_orders.append({
                "work_order_id": f"WO-{int(time.time())}-{idx+1}",
                "leak_id": leak.get("id", idx+1),
                "location_node": node,
                "severity_lpm": severity,
                "priority": priority,
                "assigned_crew": assigned_crew["id"],
                "estimated_repair_hrs": round(1.0 + (severity * 0.8), 1),
                "scheduled_start": now,
                "status": "DISPATCHED"
            })
        return work_orders
