"""
Multi-Method Fusion Engine
Combines multi-detector results into a unified, false-positive resilient detection event.

Weights come from backend/config/thresholds.yaml so the dashboard can display
the formula actually in force. They were previously hardcoded here while the UI
printed a different set, which meant the published formula did not describe the
running system.
"""
from backend.config.config_loader import thresholds_loader

_DEFAULT_WEIGHTS = {
    "mass_balance": 0.30,
    "current_signature": 0.22,
    "cusum": 0.16,
    "mnf": 0.10,
    "acoustic": 0.22,
}


class FusionEngine:
    def __init__(self, weights=None):
        configured = thresholds_loader.get("fusion.weights")
        self.weights = weights or (dict(configured) if configured else dict(_DEFAULT_WEIGHTS))

    def fuse(self, detector_results, plausibility=None):
        # A detector that reports `active: False` cannot contribute evidence —
        # the acoustic channel when no accelerometer is fitted, or when the pump
        # is off and there is no hydraulic noise to compare against. Its weight
        # is redistributed over the detectors that CAN contribute, so a rig
        # without an MPU6050 is scored on exactly the same 0-1 scale as one with
        # it, rather than having every score quietly depressed.
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

        is_alarm = total_score >= 0.35 or len(active_methods) >= 2

        # A physically impossible flow reading is not evidence, however many
        # detectors echo it. mass_balance, cusum and mnf all consume the same
        # residual, so a dead outlet meter makes three of them "agree" — enough
        # to clear both branches of the rule above. The guard (see
        # backend/detectors/plausibility.py) vetoes only when an independent
        # channel that *should* have seen a leak this size reports nothing, and
        # nothing corroborates. The score is preserved so the suppression is
        # auditable rather than invisible.
        suppressed = bool(is_alarm and plausibility and plausibility.get("implausible"))
        if suppressed:
            is_alarm = False

        return {
            "fused_score": round(total_score, 2),
            "is_alarm": is_alarm,
            "suppressed_as_implausible": suppressed,
            "suppression_reason": plausibility.get("reason") if suppressed else None,
            "active_methods": active_methods,
            "detector_count": len(detector_results),
            "contributing_count": len(contributing),
            "effective_weights": {
                r.get("method"): round(self.weights.get(r.get("method"), 0.0) / available, 4)
                for r in contributing
            },
        }
