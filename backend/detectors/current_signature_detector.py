"""
Current Signature Analysis Detector

A leak lowers the circuit's hydraulic resistance, so P1 moves to a different
point on its head-flow curve and its current shifts. INA219 or ACS712 can supply
the current measurement; only INA219 also supplies bus voltage.

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
        if current_ma is None:
            return {
                "method": "current_signature",
                "active": False,
                "unavailable_reason": "pump current sensor unavailable",
                "actual_current_ma": None,
                "current_ma": None,
                "expected_current_ma": None,
                "residual_ma": None,
                "current_delta_ma": None,
                "is_alarm": False,
                "confidence": 0.0,
            }

        # ACS712 provides current but not bus voltage. In that case the model is
        # deliberately uncorrected (nominal 12 V), and the result says so. This
        # retains a real independent current channel without inventing voltage.
        voltage_compensated = bus_v is not None
        expected_current = self.predict_expected_current(
            flow_lpm, bus_v if voltage_compensated else 12.0
        )
        residual_ma = expected_current - current_ma
        
        is_alarm = residual_ma > self.threshold_ma
        confidence = min(1.0, max(0.0, residual_ma / (self.threshold_ma * 2.0))) if is_alarm else 0.0

        return {
            "method": "current_signature",
            "active": True,
            "voltage_compensated": voltage_compensated,
            "actual_current_ma": current_ma,
            "current_ma": current_ma,  # alias for dashboard components (DetectionEngineView)
            "expected_current_ma": expected_current,
            "residual_ma": round(residual_ma, 2),
            "current_delta_ma": round(-residual_ma, 2),  # alias: negative = current dropped
            "is_alarm": is_alarm,
            "confidence": round(confidence, 2)
        }
