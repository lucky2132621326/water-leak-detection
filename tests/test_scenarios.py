"""Scenario regression suite.

Every built-in mock scenario, driven through the production pipeline and graded
against its own declared expectation. This is the system's end-to-end guard: it
catches a detector or fusion change that trades one scenario for another, which
unit tests on individual detectors cannot see.

The pass rate previously lived in a handoff document. A number in a document
does not fail a build.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.benchmark.scenario_scorer import score_scenario, verdict
from backend.mock.scenarios import BUILTIN_SCENARIOS, get_scenario

#: `manual_control` is an operator sandbox with no script and a 1-hour runtime —
#: there is nothing to grade and scoring it would add a minute to every run.
GRADED = [s for s in BUILTIN_SCENARIOS if s.id != "manual_control"]


class TestScenarioSuite(unittest.TestCase):
    def test_every_scenario_meets_its_own_expectation(self):
        failures = []
        for spec in GRADED:
            with self.subTest(scenario=spec.id):
                passed, reason = verdict(score_scenario(spec))
                if not passed:
                    failures.append(f"{spec.id}: {reason}")
                self.assertTrue(passed, f"{spec.id}: {reason}")
        self.assertEqual(failures, [], "scenarios regressed")

    def test_no_leak_scenarios_stay_completely_silent(self):
        # Precision on the control cases is the headline honesty claim: any
        # alarm here is a false positive with no leak to excuse it.
        for spec in (s for s in GRADED if not s.expect_detection):
            with self.subTest(scenario=spec.id):
                self.assertEqual(score_scenario(spec)["false_positives"], 0)

    def test_leak_scenarios_localize_to_the_right_zone(self):
        for spec in (s for s in GRADED if s.expect_zone):
            with self.subTest(scenario=spec.id):
                self.assertEqual(score_scenario(spec)["detected_zone"], spec.expect_zone)


class TestSensorFaultIsNotALeak(unittest.TestCase):
    """Regression for the outlet-meter dropout that produced 8 confirmed false
    positives at residual +5.20 L/min — the full inlet flow — because
    mass_balance and cusum both read the same broken measurement."""

    def setUp(self):
        self.scored = score_scenario(get_scenario("sensor_fault"))

    def test_dropout_raises_no_leak_alarm(self):
        self.assertEqual(self.scored["false_positives"], 0)

    def test_dropout_is_recognised_rather_than_merely_ignored(self):
        # The distinction matters: silence would mean the guard never fired and
        # the scenario passed by luck. A meter died, and the system must know it.
        self.assertGreater(self.scored["implausible_samples"], 0)


class TestSmallLeakSensitivityIsPreserved(unittest.TestCase):
    """The guard's failure mode would be suppressing genuine small leaks, whose
    hydraulic signature is legitimately below the current sensor's threshold."""

    def test_small_leak_still_detected(self):
        scored = score_scenario(get_scenario("small_leak"))
        self.assertGreater(scored["recall"], 0.5)
        self.assertEqual(scored["precision"], 1.0)
        self.assertEqual(scored["implausible_samples"], 0)

    def test_night_flow_micro_leak_still_detected(self):
        scored = score_scenario(get_scenario("night_flow"))
        self.assertGreater(scored["recall"], 0.5)
        self.assertEqual(scored["implausible_samples"], 0)


if __name__ == "__main__":
    unittest.main()
