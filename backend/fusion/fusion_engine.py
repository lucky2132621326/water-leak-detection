"""
Multi-Method Fusion Engine
Combines multi-detector results into a unified, false-positive resilient detection event.
"""
from backend.config.config_loader import thresholds_loader

# Independent physical channels: flow/current-derived methods share the same
# underlying sensors (flow meters, current), so two of them agreeing is
# weaker evidence than one of them agreeing with acoustic, which measures a
# completely different physical phenomenon (vibration, not flow balance).
_FLOW_BASED_METHODS = {"mass_balance", "current_signature", "cusum", "mnf"}


class FusionEngine:
    def __init__(self, weights=None, independent_agreement_bonus=None):
        self.weights = weights or {
            "mass_balance": 0.32,
            "current_signature": 0.20,
            "cusum": 0.16,
            "mnf": 0.12,
            "acoustic": 0.20,
        }
        self.independent_agreement_bonus = (
            independent_agreement_bonus
            if independent_agreement_bonus is not None
            else thresholds_loader.get("fusion.independent_agreement_bonus", 0.15)
        )

    def fuse(self, detector_results):
        total_score = 0.0
        active_methods = []

        for res in detector_results:
            method = res.get("method")
            weight = self.weights.get(method, 0.20)
            if res.get("is_alarm"):
                active_methods.append(method)
                total_score += weight * res.get("confidence", 1.0)

        # Acoustic is a physically independent channel from flow/current —
        # agreement between it and any flow-based method is stronger evidence
        # than either channel alone, so it earns a bonus beyond simple
        # weighted addition (hardware spec v2 section 6).
        independent_agreement = "acoustic" in active_methods and bool(_FLOW_BASED_METHODS & set(active_methods))
        if independent_agreement:
            total_score += self.independent_agreement_bonus
        total_score = min(1.0, total_score)

        is_alarm = total_score >= 0.35 or len(active_methods) >= 2

        return {
            "fused_score": round(total_score, 2),
            "is_alarm": is_alarm,
            "active_methods": active_methods,
            "detector_count": len(detector_results),
            "independent_agreement": independent_agreement,
        }
