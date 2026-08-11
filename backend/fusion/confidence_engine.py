"""
Confidence Engine
Categorizes fused multi-signal detection into explainable qualitative levels: LOW, MEDIUM, HIGH, CRITICAL.

`persistence_sec` is how long the alarm has been continuously confirmed. It
exists so that broad agreement sustained over time escalates to CRITICAL even
when no single detector is emphatic enough to push the score past 0.75 — three
independent methods holding for ten seconds is a stronger claim than one
detector reading high for one sample.

It must be supplied by the caller. Every caller passed only two arguments, so
it defaulted to 0 and that escalation branch could never evaluate true; the rule
was documented and dead. DetectionPipeline now passes the real elapsed time.
"""

class ConfidenceEngine:
    @staticmethod
    def evaluate(fused_score, active_methods_count, persistence_sec=0):
        if fused_score >= 0.75 or (active_methods_count >= 3 and persistence_sec >= 10):
            return "CRITICAL"
        elif fused_score >= 0.50 or active_methods_count >= 2:
            return "HIGH"
        elif fused_score >= 0.35:
            return "MEDIUM"
        elif fused_score > 0.0:
            return "LOW"
        return "NONE"
