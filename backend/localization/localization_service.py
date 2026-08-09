"""
Localization Service
Coordinates branch isolation testing and hydraulic zone mapping.

Rig topology (docs/HARDWARE_INTEGRATION_SPEC.md section 1): three leak tees
(A/B/C) sit upstream of a single split into Branch A (servo pinch valve, no
meter) and Branch B (Q_branch meter); both rejoin before Q_out. A leak at any
of the three tees looks IDENTICAL to the mass-balance/current/acoustic
channels — none of them can distinguish which tee without an isolation test.
So "Branch_C" is not a valid localization output: there is no sensor that
can tell tee C's signature apart from tee A/B's or the main line's. Only
three zones are ever actually distinguishable:
  - Branch_A  — confirmed by closing the servo and watching the residual drop
  - Branch_B  — confirmed by a sustained shift in Q_branch from its learned baseline
  - Main_Trunk — the leak is present but not isolated to either branch (could
    be any of the three tees, or the main line itself)
"""
from statistics import median

from backend.localization.branch_analyzer import BranchAnalyzer

# How many samples to let the residual settle after the servo closes before
# trusting an isolation-test reading. Spec section 4: "close, settle ~15s,
# take reading" — at 1 sample/sec this is a few seconds of margin past that.
_ISOLATION_SETTLE_SAMPLES = 3


class LocalizationService:
    def __init__(self):
        self.known_zones = ["Main_Trunk", "Branch_A", "Branch_B"]
        self.branch_baseline_samples = []
        self.branch_analyzer = BranchAnalyzer()
        self._pre_isolation_residual = None
        self._last_servo_state = 0
        self._samples_since_servo_closed = 0

    def observe_baseline(self, q_branch_lpm):
        self.branch_baseline_samples.append(float(q_branch_lpm))
        if len(self.branch_baseline_samples) > 120:
            self.branch_baseline_samples.pop(0)

    def localize_leak(self, residual_lpm, q_branch_lpm, servo_state_deg=0):
        servo_closed = servo_state_deg > 0

        if servo_closed and self._last_servo_state == 0:
            # Isolation test just started — snapshot the residual as it was
            # right before closing, so we have something to compare against.
            self._pre_isolation_residual = residual_lpm
            self._samples_since_servo_closed = 0
        if servo_closed:
            self._samples_since_servo_closed += 1
        else:
            self._pre_isolation_residual = None
        self._last_servo_state = servo_state_deg

        # Check the isolation-test verdict BEFORE the generic "residual too
        # small to matter" bailout below — a residual that drops to ~0 after
        # closing the servo is the STRONGEST possible confirmation the leak
        # is in Branch A, and must not be swallowed by that bailout as if it
        # meant "no leak at all."
        if (servo_closed and self._pre_isolation_residual is not None
                and self._pre_isolation_residual >= 0.1
                and self._samples_since_servo_closed >= _ISOLATION_SETTLE_SAMPLES):
            verdict = self.branch_analyzer.evaluate_isolation(
                residual_before=self._pre_isolation_residual,
                residual_after=residual_lpm,
                isolated_branch="Branch_A",
            )
            if verdict["leak_in_branch"]:
                return {
                    "zone": "Branch_A",
                    "confidence": "HIGH",
                    "evidence": f"residual dropped {verdict['residual_drop_lpm']} L/min after isolating Branch A",
                    "isolation_test": verdict,
                }
            # Isolating A didn't fix it — leak isn't in A. Fall through to
            # the checks below rather than returning early, so a negative
            # isolation result still gets a zone guess.

        if residual_lpm < 0.1:
            return {"zone": "NONE", "confidence": "NONE"}

        if len(self.branch_baseline_samples) >= 10:
            baseline = median(self.branch_baseline_samples)
            deviation = abs(q_branch_lpm - baseline)
            if deviation > max(0.20, baseline * 0.20):
                return {
                    "zone": "Branch_B",
                    "confidence": "HIGH",
                    "evidence": f"branch flow shifted {deviation:.2f} L/min from baseline",
                }

        isolation_test_completed = servo_closed and self._samples_since_servo_closed >= _ISOLATION_SETTLE_SAMPLES
        return {
            "zone": "Main_Trunk",
            "confidence": "MEDIUM",
            "evidence": (
                "isolating Branch A did not reduce the residual — leak is upstream of the split "
                "(any of tees A/B/C) or in Branch B"
                if isolation_test_completed
                else "leak evidence present but not yet isolated to a branch — run a servo "
                     "isolation test to narrow between Branch A and Main_Trunk/upstream tees"
            ),
        }
