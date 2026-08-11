"""Recovery-time regression tests.

One bug has now appeared three times in this codebase, in three different
detectors: **an unbounded trigger accumulator, so recovery time scales with how
long the leak lasted.** Each detector alarms correctly, and then stays alarming
long after the valve has shut, for a duration nobody chose.

  * `MassBalanceDetector.consecutive_triggers` — found via `small_leak`
  * `MNFDetector.consecutive_triggers`         — the same fix, never carried across
  * `CUSUMDetector.s_pos`                      — 36 minutes latched after a 2-minute leak

These tests assert the invariant that kills the whole class: **recovery time
must not depend on leak duration.** A detector that takes the same time to
stand down after a 10-second leak and a 10-minute one cannot have this bug.
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.detectors.cusum_detector import CUSUMDetector
from backend.detectors.mass_balance import MassBalanceDetector
from backend.detectors.mnf_detector import MNFDetector

#: Generous ceiling. The point is that recovery is *bounded and constant*, not
#: that it hits any particular number.
MAX_RECOVERY_SAMPLES = 60
QUIET_RESIDUAL = 0.02


def _recovery_samples(step_fn, limit=6000):
    """How many quiet samples until the detector stops alarming."""
    n = 0
    while step_fn():
        n += 1
        if n > limit:
            return limit  # effectively never
    return n


class TestCUSUMRecovery(unittest.TestCase):
    def _run_leak(self, duration_sec, rate=2.50):
        d = CUSUMDetector(slack_k=0.15, decision_h=5.0)
        for _ in range(duration_sec):
            d.analyze(rate)
        return d

    def test_accumulator_is_bounded(self):
        d = self._run_leak(600)
        self.assertLessEqual(d.s_pos, d.cap)

    def test_recovery_is_bounded(self):
        d = self._run_leak(120)
        self.assertLessEqual(
            _recovery_samples(lambda: d.analyze(QUIET_RESIDUAL)["is_alarm"]),
            MAX_RECOVERY_SAMPLES)

    def test_recovery_does_not_scale_with_leak_duration(self):
        # The invariant. A 30-second leak and a 10-minute leak must clear in
        # the same time; before the cap these differed by a factor of 20.
        short = self._run_leak(30)
        long_ = self._run_leak(600)
        self.assertEqual(
            _recovery_samples(lambda: short.analyze(QUIET_RESIDUAL)["is_alarm"]),
            _recovery_samples(lambda: long_.analyze(QUIET_RESIDUAL)["is_alarm"]))

    def test_still_detects_a_sustained_micro_leak(self):
        # The cap must not cost sensitivity — CUSUM's whole purpose is catching
        # drifts too small for an instantaneous threshold.
        d = CUSUMDetector(slack_k=0.15, decision_h=5.0)
        alarmed = any(d.analyze(0.30)["is_alarm"] for _ in range(120))
        self.assertTrue(alarmed)


class TestMNFRecovery(unittest.TestCase):
    #: 02:00 — inside the 01:00–05:00 quiet window, the only time MNF evaluates.
    BASE_TS = time.mktime(time.struct_time((2026, 8, 11, 2, 0, 0, 0, 0, -1)))

    def _run_leak(self, duration_sec, rate=0.30):
        d = MNFDetector()
        for i in range(duration_sec):
            d.analyze(self.BASE_TS + i, rate)
        return d, duration_sec

    def test_counter_is_bounded(self):
        d, _ = self._run_leak(600)
        self.assertLessEqual(d.consecutive_triggers, d.persistence_count)

    def test_recovery_does_not_scale_with_leak_duration(self):
        short, s_end = self._run_leak(30)
        long_, l_end = self._run_leak(600)
        i = [0]

        def step(d, end):
            i[0] += 1
            return d.analyze(self.BASE_TS + end + i[0], QUIET_RESIDUAL)["is_alarm"]

        i[0] = 0
        short_recovery = _recovery_samples(lambda: step(short, s_end))
        i[0] = 0
        long_recovery = _recovery_samples(lambda: step(long_, l_end))
        self.assertEqual(short_recovery, long_recovery)
        self.assertLessEqual(long_recovery, MAX_RECOVERY_SAMPLES)

    def test_still_detects_a_night_leak(self):
        d = MNFDetector()
        alarmed = any(d.analyze(self.BASE_TS + i, 0.30)["is_alarm"] for i in range(60))
        self.assertTrue(alarmed)


class TestMassBalanceRecovery(unittest.TestCase):
    """The original instance. Kept here so all three live under one invariant."""

    def _run_leak(self, duration_sec, rate=2.50):
        d = MassBalanceDetector()
        for _ in range(30):                      # settle a quiet baseline first
            d.process_sample(5.20, 5.18, 0.0)
        for _ in range(duration_sec):
            d.process_sample(5.20, 5.20 - rate, 0.0)
        return d

    def test_recovery_does_not_scale_with_leak_duration(self):
        short = self._run_leak(30)
        long_ = self._run_leak(600)
        self.assertEqual(
            _recovery_samples(lambda: short.process_sample(5.20, 5.18, 0.0)["is_alarm"]),
            _recovery_samples(lambda: long_.process_sample(5.20, 5.18, 0.0)["is_alarm"]))


if __name__ == "__main__":
    unittest.main()
