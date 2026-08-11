"""
Current Signature Analysis Detector

A leak lowers the circuit's hydraulic resistance, so P1 moves to a different
point on its head-flow curve and its current shifts. The INA219 measures that
current high-side on the 12V line.

Raw current must never be thresholded directly: it varies with supply voltage
and pump duty, so a fixed limit would fire on a sagging adapter and miss a leak
on a fresh one. The detector fits an expected-current model I = f(Q_in, bus_v)
and works on the residual against it.

This channel is PHYSICALLY INDEPENDENT of the flow meters — both meters could
drift together without moving the current signature at all. That independence is
why fusion weights it heavily and why the plausibility guard consults it.
"""

class CurrentSignatureDetector:
    def __init__(self, baseline_ma=420.0, current_drop_threshold_ma=20.0):
        self.baseline_ma = baseline_ma
        self.threshold_ma = current_drop_threshold_ma

    def predict_expected_current(self, flow_lpm, bus_v=12.0):
        """Expected draw at this flow and bus voltage.

        Motor current scales roughly with supply voltage, so the model is
        normalised against the nominal 12V rail rather than assuming it.
        """
        expected = self.baseline_ma + (flow_lpm * 2.5)
        return expected * (bus_v / 12.0) if bus_v else expected

    def analyze(self, current_ma, flow_lpm, bus_v=12.0):
        expected_current = self.predict_expected_current(flow_lpm, bus_v)
        residual_ma = expected_current - current_ma
        
        is_alarm = residual_ma > self.threshold_ma
        confidence = min(1.0, max(0.0, residual_ma / (self.threshold_ma * 2.0))) if is_alarm else 0.0

        return {
            "method": "current_signature",
            "actual_current_ma": current_ma,
            "current_ma": current_ma,  # alias for dashboard components (DetectionEngineView)
            "expected_current_ma": expected_current,
            "residual_ma": round(residual_ma, 2),
            "current_delta_ma": round(-residual_ma, 2),  # alias: negative = current dropped
            "is_alarm": is_alarm,
            "confidence": round(confidence, 2)
        }
