"""Shared Detection Pipeline

The single code path both live MQTT ingestion (backend/mqtt/subscriber.py) and
replay (backend/replay/replay_runner.py) run every sample through, so "replay
mode" is never a separately-mocked implementation — same detectors, same
fusion, same localization, same response shaping either way.
"""
from backend.detectors.detector_manager import DetectorManager
from backend.detectors.detection_state_machine import DetectionStateMachine
from backend.fusion.fusion_engine import FusionEngine
from backend.fusion.confidence_engine import ConfidenceEngine
from backend.localization.localization_service import LocalizationService
from backend.utils.pressure_estimate import estimate_pressure_bar
from backend.config.config_loader import config_loader
from backend.calibration.calibration_repository import CalibrationRepository


class DetectionPipeline:
    def __init__(self):
        self.detector_manager = DetectorManager()
        self.fusion_engine = FusionEngine()
        self.localization_service = LocalizationService()
        self.state_machine = DetectionStateMachine()
        self.alarm_onset_ts = None

    def process_sample(self, ts, q_in, q_out, q_branch, current_ma, voltage_v=12.0,
                        pump_on=True, servo_state_deg=0, pressure_bar=None):
        topology = config_loader.get("hydraulics.topology", "recombined_branch")
        bias_lpm = CalibrationRepository().get_bias()
        balance_q_branch = q_branch if topology == "metered_outflow" else 0.0
        balance_q_in = q_in - bias_lpm
        residual = balance_q_in - (q_out + balance_q_branch)

        detector_results = self.detector_manager.process_sample(
            ts, q_in, q_out, q_branch, current_ma, voltage_v,
            balance_q_in=balance_q_in,
            balance_q_branch=balance_q_branch,
        )
        fusion_result = self.fusion_engine.fuse(detector_results)
        confidence_tier = ConfidenceEngine.evaluate(fusion_result["fused_score"], len(fusion_result["active_methods"]))
        state_result = self.state_machine.update(fusion_result["is_alarm"], residual)

        if state_result["is_confirmed"]:
            if self.alarm_onset_ts is None:
                self.alarm_onset_ts = ts
            localization = self.localization_service.localize_leak(residual, q_branch, servo_state_deg)
        else:
            self.alarm_onset_ts = None
            self.localization_service.observe_baseline(q_branch)
            localization = {"zone": "NONE", "confidence": "NONE"}

        if pressure_bar is not None:
            # Replay/logged datasets carry a real authored value.
            pressure = {"pressure_bar": round(pressure_bar, 2), "source": "logged"}
        else:
            pressure = estimate_pressure_bar(residual, pump_on)

        return {
            "ts": ts,
            "residual": round(residual, 3),
            "detectors": detector_results,
            "fusion": fusion_result,
            "confidence_tier": confidence_tier,
            "state": state_result,
            "localization": localization,
            "alarm_onset_ts": self.alarm_onset_ts,
            "pressure": pressure,
            "hydraulics": {
                "topology": topology,
                "zero_leak_bias_lpm": bias_lpm,
                "branch_in_mass_balance": topology == "metered_outflow",
            }
        }
