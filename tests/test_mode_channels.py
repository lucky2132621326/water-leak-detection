"""Per-mode channel set, pressure containment, and fusion parity.

The rule this file defends: **a simulated value must never be reachable from a
live code path, and the two modes must agree about whether a given leak is a
leak.**

Those two pull against each other. Mock has one extra channel, and fusion
renormalises over whatever contributed — so the same physical leak scores lower
in mock simply because more evidence was available. That is correct on its own
terms, but it must never flip the verdict, or "mock validates live" stops being
true and every scenario result becomes meaningless.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.detectors.detector_manager import DetectorManager, methods_for_mode
from backend.fusion.fusion_engine import SENSOR_GROUPS, FusionEngine
from backend.mode import MODE_LIVE, MODE_MOCK

LIVE_CHANNELS = ["mass_balance", "current_signature", "cusum", "mnf", "acoustic", "acoustic_ml"]


class TestChannelSets(unittest.TestCase):
    def test_live_has_exactly_six_and_no_pressure(self):
        self.assertEqual(methods_for_mode(MODE_LIVE), LIVE_CHANNELS)
        self.assertNotIn("pressure_drop", methods_for_mode(MODE_LIVE))

    def test_mock_adds_pressure_and_nothing_else(self):
        self.assertEqual(methods_for_mode(MODE_MOCK), LIVE_CHANNELS + ["pressure_drop"])

    def test_live_manager_never_constructs_a_pressure_detector(self):
        self.assertIsNone(DetectorManager(mode=MODE_LIVE).pressure_detector)

    def test_mock_manager_does(self):
        self.assertIsNotNone(DetectorManager(mode=MODE_MOCK).pressure_detector)

    def test_live_results_contain_no_pressure_channel(self):
        results = DetectorManager(mode=MODE_LIVE).process_sample(
            ts=1_800_000_000, q_in=5.2, q_out=5.18, q_branch=2.1,
            current_ma=420.0, pressure_bar=2.5)  # even when handed one
        self.assertNotIn("pressure_drop", {r["method"] for r in results})


class TestSimulatedLabelling(unittest.TestCase):
    def test_pressure_result_is_labelled_simulated_never_measured(self):
        dm = DetectorManager(mode=MODE_MOCK)
        results = dm.process_sample(
            ts=1_800_000_000, q_in=5.2, q_out=5.18, q_branch=2.1,
            current_ma=420.0, pressure_bar=0.55)
        pressure = next(r for r in results if r["method"] == "pressure_drop")
        self.assertEqual(pressure["source"], "simulated")
        self.assertTrue(pressure["is_simulated"])
        self.assertIn("SIMULATED", pressure["simulated_notice"])

    def test_the_words_measured_and_estimated_never_appear(self):
        dm = DetectorManager(mode=MODE_MOCK)
        results = dm.process_sample(
            ts=1_800_000_000, q_in=5.2, q_out=5.18, q_branch=2.1,
            current_ma=420.0, pressure_bar=0.55)
        blob = str(next(r for r in results if r["method"] == "pressure_drop")).lower()
        self.assertNotIn("measured", blob)
        self.assertNotIn("estimated", blob)


class TestFusionAcrossChannelCounts(unittest.TestCase):
    def setUp(self):
        self.f = FusionEngine()

    def _results(self, alarming, include_pressure):
        methods = LIVE_CHANNELS + (["pressure_drop"] if include_pressure else [])
        return [{"method": m, "active": True, "is_alarm": m in alarming,
                 "confidence": 1.0 if m in alarming else 0.0} for m in methods]

    def test_effective_weights_sum_to_one_in_both_modes(self):
        for include in (False, True):
            with self.subTest(pressure=include):
                fused = self.f.fuse(self._results([], include))
                self.assertAlmostEqual(sum(fused["effective_weights"].values()), 1.0, places=3)

    def test_the_same_leak_is_a_leak_in_both_modes(self):
        # THE parity invariant. A small leak is visible only to the flow
        # channels; if the extra mock channel diluted it below threshold, mock
        # would stop validating live.
        for alarming in (["mass_balance", "cusum"],
                         ["mass_balance", "cusum", "current_signature"],
                         ["mass_balance"]):
            with self.subTest(alarming=alarming):
                live = self.f.fuse(self._results(alarming, False))["is_alarm"]
                mock = self.f.fuse(self._results(alarming, True))["is_alarm"]
                self.assertEqual(live, mock, f"modes disagree on {alarming}")

    def test_flow_only_agreement_does_not_trip_the_corroboration_shortcut(self):
        # mass_balance + cusum + mnf are three views of ONE residual. A dead
        # outlet meter makes all three "agree"; that is one broken measurement,
        # not three witnesses.
        fused = self.f.fuse(self._results(["mass_balance", "cusum", "mnf"], False))
        self.assertEqual(fused["independent_groups"], ["flow"])

    def test_the_two_acoustic_channels_count_as_one_group(self):
        # They share a single accelerometer. Letting them corroborate each other
        # would be the same double-count in different clothing.
        fused = self.f.fuse(self._results(["acoustic", "acoustic_ml"], False))
        self.assertEqual(fused["independent_groups"], ["vibration"])

    def test_cross_hardware_agreement_does_trip_it(self):
        fused = self.f.fuse(self._results(["mass_balance", "acoustic"], False))
        self.assertEqual(len(fused["independent_groups"]), 2)
        self.assertTrue(fused["is_alarm"])

    def test_every_weighted_method_has_a_declared_sensor_group(self):
        # A method missing from SENSOR_GROUPS would silently become its own
        # "group" and could corroborate anything.
        for method in FusionEngine().weights:
            with self.subTest(method=method):
                self.assertIn(method, SENSOR_GROUPS)

    def test_inactive_channels_are_renormalised_away(self):
        results = self._results(["mass_balance"], False)
        for r in results:
            if r["method"] in ("acoustic", "acoustic_ml"):
                r["active"] = False
        fused = self.f.fuse(results)
        self.assertNotIn("acoustic", fused["effective_weights"])
        self.assertAlmostEqual(sum(fused["effective_weights"].values()), 1.0, places=3)


if __name__ == "__main__":
    unittest.main()
