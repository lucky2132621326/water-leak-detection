"""Multi-Method Fusion Engine

Combines detector results into one false-positive-resilient verdict.

Variable channel count
----------------------
The channel set differs by mode — 6 live, 7 in mock (which adds the SIMULATED
pressure channel). Nothing here assumes a fixed set. Weights are looked up per
method and **renormalised over the detectors that actually contributed**:

    effective_weight(d) = weight(d) / sum(weight(c) for c in contributing)

so the effective weights always sum to 1.0 and `fused_score` is always on the
same 0-1 scale, whatever is present. This is what keeps confidence comparable:

  * The configured live set sums to exactly 1.00, so live scores are the weights
    as written.
  * Mock adds pressure_drop (0.18), so the divisor becomes 1.18 and every other
    channel's effective weight drops proportionally. That is correct, not a
    distortion: with more independent evidence available, any single channel is
    a smaller share of the total case. A score of 1.0 means "everything that
    could speak, did" in both modes.
  * A rig with no accelerometer renormalises over the remaining channels rather
    than being scored as if the pipe had been listened to and found quiet.

Sensor groups, not detector counts
----------------------------------
The "two independent methods agree" shortcut counts **sensor groups**, not
detectors. Several detectors share one physical measurement:

    flow       mass_balance, cusum, mnf      — three statistics of ONE residual
    current    current_signature
    vibration  acoustic, acoustic_ml         — same accelerometer, two methods
    pressure   pressure_drop                 — mock only, SIMULATED

Counting detectors instead would let a dead outlet meter trip the rule with
three flow detectors "agreeing" on one broken number, or let the rule-based and
ML acoustic channels agree with each other about a single microphone. Neither is
corroboration. Requiring two distinct groups means agreement has to cross
hardware to count.
"""
from backend.config.config_loader import thresholds_loader

_DEFAULT_WEIGHTS = {
    "mass_balance": 0.30,
    "current_signature": 0.20,
    "cusum": 0.16,
    "mnf": 0.08,
    "acoustic": 0.13,
    "acoustic_ml": 0.13,
    # Mock only. Absent from live, where renormalisation simply omits it.
    "pressure_drop": 0.18,
}

#: Which physical measurement each detector reads. Detectors sharing a group are
#: NOT independent evidence of one another.
SENSOR_GROUPS = {
    "mass_balance": "flow",
    "cusum": "flow",
    "mnf": "flow",
    "current_signature": "current",
    "acoustic": "vibration",
    "acoustic_ml": "vibration",
    "pressure_drop": "pressure",
}

#: Fused score at or above which a single-channel case is strong enough alone.
SCORE_ALARM_THRESHOLD = 0.35
#: Independent sensor groups that must agree for the corroboration shortcut.
MIN_INDEPENDENT_GROUPS = 2


class FusionEngine:
    def __init__(self, weights=None):
        configured = thresholds_loader.get("fusion.weights")
        self.weights = weights or (dict(configured) if configured else dict(_DEFAULT_WEIGHTS))

    def fuse(self, detector_results, plausibility=None):
        # A detector reporting `active: False` cannot contribute — no
        # accelerometer fitted, no model bundle loaded, pump off, or (in live) a
        # channel that simply is not part of this mode's set. Its weight is
        # redistributed rather than counted as a silent vote for "no leak".
        contributing = [r for r in detector_results if r.get("active", True)]
        available = sum(self.weights.get(r.get("method"), 0.0) for r in contributing) or 1.0

        total_score = 0.0
        active_methods = []

        for res in contributing:
            method = res.get("method")
            weight = self.weights.get(method, 0.0) / available
            if res.get("is_alarm"):
                active_methods.append(method)
                total_score += weight * res.get("confidence", 1.0)

        alarming_groups = {SENSOR_GROUPS.get(m, m) for m in active_methods}
        is_alarm = (total_score >= SCORE_ALARM_THRESHOLD
                    or len(alarming_groups) >= MIN_INDEPENDENT_GROUPS)

        # A physically impossible flow reading is not evidence, however many
        # detectors echo it. The guard (backend/detectors/plausibility.py) vetoes
        # only when an independent channel that *should* have seen a leak this
        # size reports nothing, and nothing corroborates. The score is preserved
        # so the suppression is auditable rather than invisible.
        suppressed = bool(is_alarm and plausibility and plausibility.get("implausible"))
        if suppressed:
            is_alarm = False

        return {
            "fused_score": round(total_score, 2),
            "is_alarm": is_alarm,
            "suppressed_as_implausible": suppressed,
            "suppression_reason": plausibility.get("reason") if suppressed else None,
            "active_methods": active_methods,
            #: Distinct hardware backing the alarm — the number that actually
            #: says how corroborated this is.
            "independent_groups": sorted(alarming_groups),
            "detector_count": len(detector_results),
            "contributing_count": len(contributing),
            "effective_weights": {
                r.get("method"): round(self.weights.get(r.get("method"), 0.0) / available, 4)
                for r in contributing
            },
        }
