"""
CUSUM (Cumulative Sum) Residual Detector
Detects small, persistent micro-leaks below 3-Sigma instantaneous thresholds.
"""

class CUSUMDetector:
    def __init__(self, slack_k=0.15, decision_h=3.0, reset_after_normal_samples=10):
        self.k = slack_k  # Reference value slack
        self.h = decision_h  # Decision boundary threshold
        self.s_pos = 0.0
        self.reset_after_normal_samples = reset_after_normal_samples
        self.consecutive_normal = 0

    def reset(self):
        self.s_pos = 0.0
        self.consecutive_normal = 0

    def analyze(self, residual_lpm):
        # Accumulate positive residual deviation above slack k
        self.s_pos = max(0.0, self.s_pos + (residual_lpm - self.k))

        # A one-sided CUSUM can otherwise remain saturated for minutes after a
        # confirmed leak ends. Ten consecutive below-slack samples represent a
        # stable recovery window and re-arm the detector for the next event.
        if residual_lpm <= self.k:
            self.consecutive_normal += 1
            if self.consecutive_normal >= self.reset_after_normal_samples:
                self.s_pos = 0.0
        else:
            self.consecutive_normal = 0
        
        is_alarm = self.s_pos >= self.h
        confidence = min(1.0, max(0.0, self.s_pos / (self.h * 1.5))) if is_alarm else round(self.s_pos / self.h, 2)

        return {
            "method": "cusum",
            "cusum_score": round(self.s_pos, 2),
            "threshold_h": self.h,
            "recovery_samples": self.consecutive_normal,
            "is_alarm": is_alarm,
            "confidence": round(confidence, 2)
        }
