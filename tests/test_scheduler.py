"""CP-SAT work-order scheduler tests.

The previous implementation was `crews[idx % len(crews)]` with a hardcoded start
time while calling itself a CP-SAT scheduler. These tests pin the properties a
real solver must satisfy, so a regression to round-robin would fail rather than
merely look plausible.
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.scheduler.cp_sat_scheduler import CPSatWorkOrderScheduler

BASE_TS = 1786348000


class TestScheduler(unittest.TestCase):
    def setUp(self):
        self.s = CPSatWorkOrderScheduler()

    def schedule(self, leaks):
        return self.s.optimize_schedule(leaks, start_epoch=BASE_TS)

    def test_empty_input(self):
        self.assertEqual(self.schedule([]), [])

    def test_solver_actually_runs(self):
        orders = self.schedule([{"id": "L1", "location_node": "Branch_A", "severity_lpm": 1.0}])
        self.assertEqual(len(orders), 1)
        self.assertIn("CP-SAT", orders[0]["solver_status"])

    def test_every_leak_assigned_exactly_once(self):
        leaks = [{"id": f"L{i}", "location_node": "Branch_A", "severity_lpm": 1.0} for i in range(5)]
        orders = self.schedule(leaks)
        self.assertEqual(len(orders), 5)
        self.assertEqual(sorted(o["leak_id"] for o in orders), sorted(l["id"] for l in leaks))

    def test_crew_skill_is_respected(self):
        # Main_Trunk requires MAIN_TRUNK, which only CREW_GAMMA holds.
        orders = self.schedule([{"id": "L1", "location_node": "Main_Trunk", "severity_lpm": 2.0}])
        self.assertEqual(orders[0]["assigned_crew"], "CREW_GAMMA")

    def test_severity_drives_priority(self):
        orders = self.schedule([
            {"id": "big", "location_node": "Branch_A", "severity_lpm": 2.0},
            {"id": "small", "location_node": "Branch_A", "severity_lpm": 0.1},
        ])
        by_id = {o["leak_id"]: o for o in orders}
        self.assertEqual(by_id["big"]["priority"], "URGENT")
        self.assertEqual(by_id["small"]["priority"], "NORMAL")

    def test_severe_leak_scheduled_before_minor_on_same_crew(self):
        # Both need CREW_ALPHA's skill, so they must be sequenced — the solver
        # minimises severity-weighted completion, which puts the big one first.
        orders = self.schedule([
            {"id": "minor", "location_node": "Branch_A", "severity_lpm": 0.2},
            {"id": "major", "location_node": "Branch_A", "severity_lpm": 2.4},
        ])
        by_id = {o["leak_id"]: o for o in orders}
        self.assertLess(by_id["major"]["queue_offset_min"], by_id["minor"]["queue_offset_min"])

    def test_same_crew_jobs_do_not_overlap(self):
        leaks = [{"id": f"L{i}", "location_node": "Branch_A", "severity_lpm": 1.0} for i in range(4)]
        orders = self.schedule(leaks)
        by_crew = {}
        for o in orders:
            by_crew.setdefault(o["assigned_crew"], []).append(o)
        for crew_orders in by_crew.values():
            crew_orders.sort(key=lambda o: o["queue_offset_min"])
            for a, b in zip(crew_orders, crew_orders[1:]):
                finish_a = a["queue_offset_min"] + a["estimated_repair_hrs"] * 60
                self.assertLessEqual(finish_a, b["queue_offset_min"] + 1e-6,
                                     f"{a['leak_id']} overlaps {b['leak_id']} on {a['assigned_crew']}")

    def test_parallel_crews_are_used(self):
        # Three leaks needing three different skills should run concurrently
        # rather than being queued behind one another.
        orders = self.schedule([
            {"id": "A", "location_node": "Branch_A", "severity_lpm": 1.0},
            {"id": "B", "location_node": "Branch_B", "severity_lpm": 1.0},
            {"id": "C", "location_node": "Main_Trunk", "severity_lpm": 1.0},
        ])
        self.assertEqual(len({o["assigned_crew"] for o in orders}), 3)
        self.assertTrue(all(o["queue_offset_min"] == 0 for o in orders))

    def test_bigger_leaks_take_longer(self):
        orders = self.schedule([
            {"id": "small", "location_node": "Branch_A", "severity_lpm": 0.2},
            {"id": "big", "location_node": "Main_Trunk", "severity_lpm": 2.5},
        ])
        by_id = {o["leak_id"]: o for o in orders}
        self.assertGreater(by_id["big"]["estimated_repair_hrs"], by_id["small"]["estimated_repair_hrs"])

    def test_scheduled_start_is_derived_not_hardcoded(self):
        # The old implementation returned a fixed "2026-08-03 10:30:00" string.
        a = self.s.optimize_schedule([{"id": "L", "location_node": "Branch_A", "severity_lpm": 1.0}], start_epoch=BASE_TS)
        b = self.s.optimize_schedule([{"id": "L", "location_node": "Branch_A", "severity_lpm": 1.0}], start_epoch=BASE_TS + 7200)
        self.assertNotEqual(a[0]["scheduled_start"], b[0]["scheduled_start"])
        self.assertEqual(b[0]["scheduled_start_ts"] - a[0]["scheduled_start_ts"], 7200)

    def test_unknown_location_still_schedules(self):
        orders = self.schedule([{"id": "L", "location_node": "Unmapped_Zone", "severity_lpm": 1.0}])
        self.assertEqual(len(orders), 1)
        self.assertIn(orders[0]["assigned_crew"], {c["id"] for c in self.s.crews})

    def test_greedy_fallback_is_labelled_honestly(self):
        # With no eligible crew, CP-SAT is infeasible and the fallback runs —
        # and must say so rather than presenting itself as an optimal solve.
        s = CPSatWorkOrderScheduler(crews=[
            {"id": "CREW_ONLY", "skills": ["NOTHING_USEFUL"], "location": "Zone_9", "status": "AVAILABLE"},
        ])
        orders = s.optimize_schedule(
            [{"id": "L", "location_node": "Main_Trunk", "severity_lpm": 1.0}], start_epoch=BASE_TS)
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0]["solver_status"], "GREEDY FALLBACK")


if __name__ == "__main__":
    unittest.main()
