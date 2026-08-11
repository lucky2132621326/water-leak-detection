"""Localization tests.

The rig offers two signals of very different quality (spec Part A.1):

  * the **MG996R pinch valve on Branch A** — a step test, and direct causal
    evidence: pinch the branch, see whether the residual collapses
  * **Flow 3 on Branch B** — the branch INLET meter, which reads the same
    whether or not anything downstream of it is leaking

The weak signal used to be tested first and reported as HIGH confidence, so a
Branch B diagnosis was overwritten by mere branch flow — dispatching a crew to
the wrong pipe.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.localization.localization_service import LocalizationService


class TestStepTestEvidence(unittest.TestCase):
    """A closed pinch valve is the strongest inference the rig can make."""

    def setUp(self):
        self.loc = LocalizationService()

    def test_pinched_branch_with_persisting_residual_clears_branch_a(self):
        # Branch A is pinched shut and water is STILL going missing, so the loss
        # is not on Branch A. That is a causal conclusion, not a correlation.
        result = self.loc.localize_leak(1.0, q_branch_lpm=0.0, servo_state_deg=90)
        self.assertEqual(result["zone"], "Main_Trunk")
        self.assertEqual(result["confidence"], "HIGH")
        self.assertIn("step test", result["basis"])

    def test_pinched_branch_with_branch_b_flowing_points_at_branch_b(self):
        result = self.loc.localize_leak(1.0, q_branch_lpm=2.1, servo_state_deg=90)
        self.assertEqual(result["zone"], "Branch_B")
        self.assertEqual(result["confidence"], "HIGH")

    def test_step_test_outranks_branch_flow(self):
        # The original bug: branch flow was checked first, so this returned
        # Branch_A with HIGH confidence regardless of the valve.
        self.assertNotEqual(
            self.loc.localize_leak(1.0, q_branch_lpm=2.1, servo_state_deg=90)["zone"],
            "Branch_A")


class TestWeakEvidenceIsLabelledWeak(unittest.TestCase):
    def setUp(self):
        self.loc = LocalizationService()

    def test_branch_flow_without_a_step_test_is_low_confidence(self):
        # Flow 3 meters the branch inlet. A leak downstream of it does not
        # reduce that reading, so branch flow says the branch is in use — never
        # that it is leaking. HIGH was never justifiable.
        result = self.loc.localize_leak(1.0, q_branch_lpm=2.1, servo_state_deg=0)
        self.assertEqual(result["confidence"], "LOW")
        self.assertIn("isolate", result["basis"])

    def test_main_trunk_when_nothing_points_at_a_branch(self):
        result = self.loc.localize_leak(1.0, q_branch_lpm=0.0, servo_state_deg=0)
        self.assertEqual(result["zone"], "Main_Trunk")
        self.assertEqual(result["confidence"], "MEDIUM")

    def test_no_zone_below_the_residual_floor(self):
        result = self.loc.localize_leak(0.05, q_branch_lpm=2.1, servo_state_deg=90)
        self.assertEqual(result["zone"], "NONE")
        self.assertEqual(result["confidence"], "NONE")

    def test_every_result_explains_which_signal_it_used(self):
        for servo, branch in ((90, 0.0), (0, 2.1), (0, 0.0)):
            with self.subTest(servo=servo, branch=branch):
                self.assertIn("basis", self.loc.localize_leak(1.0, branch, servo))


if __name__ == "__main__":
    unittest.main()
