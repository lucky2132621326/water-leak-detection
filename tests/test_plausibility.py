"""Tests for the physical plausibility guard.

The guard's value is entirely in *when it declines to act*. A guard that vetoes
too eagerly suppresses real leaks, which is far worse than the false positive it
was built to remove — so most of these tests assert that it stays out of the way.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.detectors.plausibility import PlausibilityGuard
from backend.fusion.fusion_engine import FusionEngine


def flow_alarm(residual, method="mass_balance"):
    return {"method": method, "is_alarm": True, "confidence": 1.0, "residual": residual}


def current(is_alarm, residual_ma):
    """`residual_ma` is expected-minus-actual: how much current went missing."""
    return {"method": "current_signature", "is_alarm": is_alarm, "confidence": 1.0,
            "residual_ma": residual_ma}


def acoustic(is_alarm, ratio, active=True, threshold=1.8):
    """`ratio` is band_mid over the rig's own clean baseline. ~1.0 means silent."""
    return {"method": "acoustic", "is_alarm": is_alarm, "confidence": 1.0,
            "active": active, "ratio": ratio, "ratio_threshold": threshold}


class TestGuardVetoes(unittest.TestCase):
    """The case the guard exists for: a dead outlet meter."""

    def setUp(self):
        self.guard = PlausibilityGuard()

    def test_outlet_dropout_is_ruled_implausible(self):
        # Residual = the entire 5.20 L/min inlet flow, while the pump current and
        # the pipe itself sit at baseline. Water cannot escape that fast in
        # silence: a dead meter makes no sound, a real leak jets audibly.
        v = self.guard.evaluate(
            5.20,
            [flow_alarm(5.20), flow_alarm(5.20, "cusum"),
             current(False, 2.0), acoustic(False, 1.02)],
            q_in=5.20,
        )
        self.assertTrue(v["implausible"])
        self.assertIn("current_signature", v["contradicting"])
        self.assertIn("acoustic", v["contradicting"])

    def test_names_the_faulty_instrument(self):
        v = self.guard.evaluate(
            5.20, [flow_alarm(5.20), current(False, 2.0), acoustic(False, 1.02)], q_in=5.20)
        self.assertIn("outlet flow meter", v["fault_hypothesis"])

    def test_one_contradicting_channel_is_enough(self):
        # No accelerometer fitted. Pump current alone still refutes.
        v = self.guard.evaluate(
            5.20,
            [flow_alarm(5.20), current(False, 2.0), acoustic(False, 1.0, active=False)],
            q_in=5.20,
        )
        self.assertTrue(v["implausible"])
        self.assertEqual(v["contradicting"], ["current_signature"])

    def test_fusion_withholds_the_alarm_and_says_so(self):
        results = [flow_alarm(5.20), flow_alarm(5.20, "cusum"),
                   current(False, 2.0), acoustic(False, 1.02)]
        verdict = self.guard.evaluate(5.20, results, q_in=5.20)
        fused = FusionEngine().fuse(results, plausibility=verdict)
        self.assertFalse(fused["is_alarm"])
        self.assertTrue(fused["suppressed_as_implausible"])
        self.assertIsNotNone(fused["suppression_reason"])
        # The score itself is preserved — suppression must be auditable.
        self.assertGreater(fused["fused_score"], 0.0)


class TestGuardStandsAside(unittest.TestCase):
    """Every case where vetoing would cost real detections."""

    def setUp(self):
        self.guard = PlausibilityGuard()

    def test_small_leak_survives_a_silent_current_channel(self):
        # 0.30 L/min predicts a ~10 mA drop — under the 25 mA threshold, so the
        # current detector is CORRECT to stay quiet. Vetoing on that silence
        # would suppress exactly the leaks this system is most valuable for.
        v = self.guard.evaluate(
            0.30, [flow_alarm(0.30), current(False, 9.0), acoustic(False, 1.05)], q_in=5.20)
        self.assertFalse(v["implausible"])

    def test_mid_size_leak_below_the_hard_floor_survives(self):
        v = self.guard.evaluate(
            0.70, [flow_alarm(0.70), current(False, 1.0), acoustic(False, 1.0)], q_in=5.20)
        self.assertFalse(v["implausible"])
        self.assertIn("floor", v["reason"])

    def test_large_leak_with_corroborating_current_survives(self):
        v = self.guard.evaluate(
            2.50, [flow_alarm(2.50), current(True, 87.5), acoustic(False, 1.10)], q_in=5.20)
        self.assertFalse(v["implausible"])
        self.assertEqual(v["corroborating"], ["current_signature"])

    def test_any_corroboration_outranks_a_contradiction(self):
        # Current refutes, acoustic confirms. Genuine hydraulic evidence exists,
        # so the alarm stands and the disagreement is left for a human.
        v = self.guard.evaluate(
            5.20, [flow_alarm(5.20), current(False, 1.0), acoustic(True, 3.40)], q_in=5.20)
        self.assertFalse(v["implausible"])

    def test_absent_accelerometer_cannot_contradict(self):
        # A rig with no MPU6050 has not listened to the pipe. Silence it never
        # heard is not evidence of anything.
        v = self.guard.evaluate(
            5.20,
            [flow_alarm(5.20), acoustic(False, 1.0, active=False)],
            q_in=5.20,
        )
        self.assertFalse(v["implausible"])

    def test_no_veto_without_a_flow_alarm(self):
        v = self.guard.evaluate(
            5.20, [current(False, 0.0), acoustic(False, 1.0)], q_in=5.20)
        self.assertFalse(v["implausible"])

    def test_pump_off_disables_the_guard(self):
        # With the pump off there is no hydraulic signature to predict against.
        v = self.guard.evaluate(
            5.20, [flow_alarm(5.20), current(False, 0.0), acoustic(False, 1.0)],
            pump_on=False, q_in=5.20)
        self.assertFalse(v["implausible"])

    def test_uncalibrated_rig_fails_open(self):
        # A zeroed calibration constant means the current channel can predict
        # nothing, and with no accelerometer fitted neither can acoustic. The
        # guard must then never veto, rather than veto on garbage arithmetic.
        guard = PlausibilityGuard(current_ma_per_leak_lpm=0.0)
        v = guard.evaluate(
            5.20, [flow_alarm(5.20), current(False, 0.0), acoustic(False, 1.0, active=False)],
            q_in=5.20)
        self.assertFalse(v["implausible"])

    def test_disabled_guard_is_inert(self):
        guard = PlausibilityGuard(enabled=False)
        v = guard.evaluate(
            5.20, [flow_alarm(5.20), current(False, 0.0), acoustic(False, 1.0)], q_in=5.20)
        self.assertFalse(v["implausible"])

    def test_fusion_without_a_verdict_is_unchanged(self):
        # Every existing caller passes no plausibility argument; none may change.
        results = [flow_alarm(5.20), flow_alarm(5.20, "cusum")]
        self.assertTrue(FusionEngine().fuse(results)["is_alarm"])
        self.assertFalse(FusionEngine().fuse(results)["suppressed_as_implausible"])


if __name__ == "__main__":
    unittest.main()
