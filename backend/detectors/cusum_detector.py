"""
CUSUM (Cumulative Sum) Residual Detector
Detects small, persistent micro-leaks below 3-Sigma instantaneous thresholds.

The accumulator is deliberately capped — see `analyze`. Left unbounded, this
detector's recovery time scales with how long the leak lasted, which is the
same defect already found and fixed in MassBalanceDetector and MNFDetector.
"""

class CUSUMDetector:
    def __init__(self, slack_k=0.15, decision_h=3.0, cap_multiple=2.0):
        self.k = slack_k  # Reference value slack
        self.h = decision_h  # Decision boundary threshold
        #: Ceiling on the accumulator, as a multiple of h. This is what bounds
        #: recovery time; see the comment in `analyze`.
        self.cap = decision_h * cap_multiple
        self.s_pos = 0.0

    def reset(self):
        self.s_pos = 0.0

    def analyze(self, residual_lpm):
        # Accumulate positive residual deviation above slack k, then clamp.
        #
        # The clamp is not cosmetic. This statistic only decays at (k - residual)
        # per sample — about 0.13 L/min on a quiet rig — so whatever it climbs to
        # during a leak, it must walk back down at that crawl afterwards. A
        # 2-minute 2.5 L/min leak drove it to 286, which needs ~2,160 samples
        # (36 minutes) to fall back under h. The detector sat latched in alarm
        # that whole time, long after the valve had shut.
        #
        # That is the third appearance of one bug: recovery time scaling with
        # leak duration, already fixed by capping in MassBalanceDetector
        # (consecutive_triggers) and MNFDetector. Capping at a small multiple of
        # h bounds recovery to a fixed ~38 samples regardless of how large or
        # long the leak was, while losing nothing — every value above h means
        # the same thing operationally, and confidence already saturates at 1.5h.
        self.s_pos = min(self.cap, max(0.0, self.s_pos + (residual_lpm - self.k)))

        is_alarm = self.s_pos >= self.h
        confidence = min(1.0, max(0.0, self.s_pos / (self.h * 1.5))) if is_alarm else round(self.s_pos / self.h, 2)

        return {
            "method": "cusum",
            "cusum_score": round(self.s_pos, 2),
            "threshold_h": self.h,
            "is_alarm": is_alarm,
            "confidence": round(confidence, 2)
        }
