"""
Localization Service
Coordinates branch isolation testing and hydraulic zone mapping.
"""
from statistics import median

class LocalizationService:
    def __init__(self):
        self.known_zones = ["Main_Trunk", "Branch_A", "Branch_B", "Branch_C"]
        self.branch_baseline_samples = []

    def observe_baseline(self, q_branch_lpm):
        self.branch_baseline_samples.append(float(q_branch_lpm))
        if len(self.branch_baseline_samples) > 120:
            self.branch_baseline_samples.pop(0)

    def localize_leak(self, residual_lpm, q_branch_lpm, servo_state_deg=0):
        if residual_lpm < 0.1:
            return {"zone": "NONE", "confidence": "NONE"}

        if servo_state_deg > 0:
            return {"zone": "Branch_A", "confidence": "HIGH"}

        if len(self.branch_baseline_samples) >= 10:
            baseline = median(self.branch_baseline_samples)
            deviation = abs(q_branch_lpm - baseline)
            if deviation > max(0.20, baseline * 0.20):
                return {
                    "zone": "Branch_B",
                    "confidence": "HIGH",
                    "evidence": f"branch flow shifted {deviation:.2f} L/min from baseline",
                }

        return {"zone": "Main_Trunk", "confidence": "MEDIUM"}
