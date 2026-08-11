"""Alert lifecycle tests.

Runs entirely against an in-memory AlertService (enable_persistence=False), so
the suite needs no MongoDB and never reads or writes real incident data.
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.alerts.alert_service import AlertService


def make_response(ts, is_alarm=True, residual=1.25, zone="Branch_A",
                  tier="HIGH", likelihood=60.0, methods=None):
    return {
        "ts": ts,
        "residual": residual,
        "is_alarm": is_alarm,
        "likelihood_score": likelihood,
        "confidence_tier": tier,
        "zone": zone if is_alarm else "NONE",
        "evidence": f"flow residual +{residual:.2f} L/min",
        "active_methods": methods or ["mass_balance"],
        "false_positive_warning": {"disclaimer": "indicative", "estimated_false_positive_rate": 0.03},
        "work_order_summary": {"summary": "Inspect Branch_A.", "source": "template"},
    }


class AlertServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.svc = AlertService(enable_persistence=False)


class TestIngestion(AlertServiceTestCase):
    def test_no_alarm_creates_nothing(self):
        self.assertIsNone(self.svc.ingest(make_response(100, is_alarm=False)))
        self.assertEqual(self.svc.counts()["total"], 0)

    def test_consecutive_alarms_merge_into_one_incident(self):
        for ts in range(100, 110):
            self.svc.ingest(make_response(ts))
        self.assertEqual(self.svc.counts()["total"], 1)
        alert = self.svc.query()[0]
        self.assertEqual(alert["sample_count"], 10)
        self.assertEqual(alert["duration_sec"], 9.0)

    def test_alarm_clearing_closes_the_window_but_keeps_it_active(self):
        for ts in range(100, 105):
            self.svc.ingest(make_response(ts))
        self.svc.ingest(make_response(105, is_alarm=False))
        alert = self.svc.query()[0]
        self.assertFalse(alert["is_open"])
        self.assertEqual(alert["status"], "ACTIVE")  # still needs a disposition
        self.assertEqual(alert["end_ts"], 104)

    def test_distant_alarm_starts_a_new_incident(self):
        self.svc.ingest(make_response(100))
        self.svc.ingest(make_response(101, is_alarm=False))
        # Well beyond merge_gap_sec — a genuinely separate event.
        self.svc.ingest(make_response(100 + int(self.svc.merge_gap_sec) + 500))
        self.assertEqual(self.svc.counts()["total"], 2)

    def test_replaying_the_same_window_is_idempotent(self):
        # The replay player loops a stored run forever; re-ingesting the same
        # timestamps must not accumulate duplicate incidents.
        def one_pass():
            for ts in range(100, 110):
                self.svc.ingest(make_response(ts))
            self.svc.ingest(make_response(110, is_alarm=False))

        for _ in range(5):
            one_pass()
        self.assertEqual(self.svc.counts()["total"], 1)

    def test_peak_rate_is_retained_not_last_value(self):
        self.svc.ingest(make_response(100, residual=0.4))
        self.svc.ingest(make_response(101, residual=2.0))
        self.svc.ingest(make_response(102, residual=0.3))
        alert = self.svc.query()[0]
        self.assertEqual(alert["peak_leak_rate_lpm"], 2.0)
        self.assertEqual(alert["leak_rate_lpm"], 0.3)
        self.assertEqual(alert["impact"]["severity"], "CRITICAL")  # from the peak

    def test_negative_residual_never_becomes_a_leak_rate(self):
        self.svc.ingest(make_response(100, residual=-1.5))
        self.assertEqual(self.svc.query()[0]["peak_leak_rate_lpm"], 0.0)


class TestLifecycle(AlertServiceTestCase):
    def setUp(self):
        super().setUp()
        # Deliberately "live": savings is an operational KPI and excludes mock
        # incidents by default, so a mock-sourced alert would correctly credit
        # nothing and these assertions would be testing the wrong thing.
        for ts in range(100, 105):
            self.svc.ingest(make_response(ts, residual=1.0), source="live")
        self.alert_id = self.svc.query()[0]["alert_id"]

    def test_resolve_credits_savings(self):
        alert = self.svc.resolve(self.alert_id, note="Clamp replaced")
        self.assertEqual(alert["status"], "RESOLVED")
        # 1.0 L/min prevented over the 30-day horizon = 43,200 L.
        self.assertAlmostEqual(alert["water_saved_litres"], 43200.0, places=1)
        self.assertEqual(self.svc.savings()["leaks_prevented"], 1)

    def test_false_positive_credits_nothing(self):
        alert = self.svc.mark_false_positive(self.alert_id)
        self.assertEqual(alert["status"], "FALSE_POSITIVE")
        self.assertEqual(alert["water_saved_litres"], 0.0)
        self.assertEqual(self.svc.savings()["water_saved_litres"], 0.0)
        self.assertEqual(self.svc.savings()["false_positives"], 1)

    def test_reopen_reverses_the_savings_credit(self):
        self.svc.resolve(self.alert_id)
        self.assertGreater(self.svc.savings()["water_saved_litres"], 0)
        self.svc.reopen(self.alert_id)
        self.assertEqual(self.svc.savings()["water_saved_litres"], 0.0)
        self.assertEqual(self.svc.query()[0]["status"], "ACTIVE")

    def test_resolving_twice_does_not_double_count(self):
        self.svc.resolve(self.alert_id)
        first = self.svc.savings()["water_saved_litres"]
        self.svc.resolve(self.alert_id)
        self.assertEqual(self.svc.savings()["water_saved_litres"], first)

    def test_unknown_alert_returns_none(self):
        self.assertIsNone(self.svc.resolve("LEAK-9999"))
        self.assertIsNone(self.svc.mark_false_positive("LEAK-9999"))

    def test_precision_reflects_dispositions(self):
        self.svc.resolve(self.alert_id)
        self.svc.ingest(make_response(10_000, residual=1.0), source="live")
        self.svc.mark_false_positive(self.svc.query(status="ACTIVE")[0]["alert_id"])
        self.assertEqual(self.svc.savings()["detection_precision"], 0.5)

    def test_reingest_after_disposition_does_not_undo_it(self):
        self.svc.resolve(self.alert_id)
        for ts in range(100, 105):
            self.svc.ingest(make_response(ts, residual=1.0), source="live")
        self.assertEqual(self.svc.get(self.alert_id)["status"], "RESOLVED")
        self.assertEqual(self.svc.counts()["total"], 1)


class TestMockExclusion(AlertServiceTestCase):
    """Synthetic incidents must not inflate operational KPIs.

    Crediting water "saved" on a leak that never physically existed would make
    the figure meaningless, so mock-sourced alerts are excluded by default and
    only counted when explicitly asked for.
    """

    def setUp(self):
        super().setUp()
        for ts in range(100, 105):
            self.svc.ingest(make_response(ts, residual=1.0), source="live")
        for ts in range(5000, 5005):
            self.svc.ingest(make_response(ts, residual=2.0), source="mock")
        for a in self.svc.query():
            self.svc.resolve(a["alert_id"])

    def test_every_incident_in_the_store_is_counted(self):
        """Live and mock now live in physically separate databases with one
        AlertService instance each, so there is nothing to filter: a per-mode
        store cannot contain the other mode's incidents. The old
        `include_mock` filter would have returned nothing at all in mock mode.
        """
        s = self.svc.savings()
        self.assertEqual(s["leaks_prevented"], 2)
        # 1.0 + 2.0 L/min over the 30-day horizon.
        self.assertAlmostEqual(s["water_saved_litres"], 129600.0, places=1)

    def test_savings_declare_which_mode_produced_them(self):
        # Mock savings are real arithmetic over synthetic leaks: fine as a
        # demonstration, meaningless as an operational claim. The flag is what
        # stops the UI presenting one as the other.
        s = self.svc.savings()
        self.assertEqual(s["mode"], "mock")
        self.assertTrue(s["is_synthetic"])

    def test_counts_are_scoped_to_this_mode(self):
        counts = self.svc.counts()
        self.assertEqual(counts["total"], 2)
        self.assertEqual(counts["mode"], "mock")


class TestQueries(AlertServiceTestCase):
    def setUp(self):
        super().setUp()
        self.svc.ingest(make_response(1000, residual=1.5, zone="Branch_A", likelihood=80.0))
        self.svc.ingest(make_response(1001, is_alarm=False))
        self.svc.ingest(make_response(5000, residual=0.3, zone="Branch_B", likelihood=40.0))
        self.svc.ingest(make_response(5001, is_alarm=False))

    def test_filter_by_zone(self):
        self.assertEqual(len(self.svc.query(zone="Branch_A")), 1)
        self.assertEqual(len(self.svc.query(zone="ALL")), 2)

    def test_filter_by_severity(self):
        self.assertEqual(len(self.svc.query(severity="CRITICAL")), 1)
        self.assertEqual(len(self.svc.query(severity="MODERATE")), 1)
        self.assertEqual(len(self.svc.query(severity="MINOR")), 0)

    def test_filter_by_confidence_and_time(self):
        self.assertEqual(len(self.svc.query(min_confidence=50)), 1)
        self.assertEqual(len(self.svc.query(since_ts=2000)), 1)
        self.assertEqual(len(self.svc.query(until_ts=2000)), 1)

    def test_search_matches_id_and_zone(self):
        self.assertEqual(len(self.svc.query(search="branch_b")), 1)
        self.assertEqual(len(self.svc.query(search="LEAK-")), 2)
        self.assertEqual(len(self.svc.query(search="nonexistent")), 0)

    def test_results_are_newest_first(self):
        rows = self.svc.query()
        self.assertGreater(rows[0]["start_ts"], rows[1]["start_ts"])

    def test_zones_listing(self):
        self.assertEqual(self.svc.zones(), ["Branch_A", "Branch_B"])


if __name__ == "__main__":
    unittest.main()
