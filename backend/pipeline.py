"""Shared Detection Pipeline

The single code path every sample runs through, in both operating modes — same
detectors, same fusion, same plausibility guard, same localization, same response
shaping. Switching modes changes where data comes from, never how it is judged.
"""
from backend.detectors.detection_state_machine import DetectionStateMachine
from backend.detectors.detector_manager import DetectorManager
from backend.detectors.plausibility import PlausibilityGuard
from backend.detectors.residual import compute_residual, describe_topology
from backend.fusion.confidence_engine import ConfidenceEngine
from backend.fusion.fusion_engine import FusionEngine
from backend.localization.localization_service import LocalizationService


class DetectionPipeline:
    def __init__(self):
        self.detector_manager = DetectorManager()
        self.fusion_engine = FusionEngine()
        self.localization_service = LocalizationService()
        self.state_machine = DetectionStateMachine()
        self.plausibility_guard = PlausibilityGuard()
        self.alarm_onset_ts = None

    def process_sample(self, ts, q_in, q_out, q_branch, current_ma, bus_v=12.0,
                       pump_on=True, servo_state_deg=0, vibration=None,
                       water_c=None, voltage_v=None):
        if voltage_v is not None:
            bus_v = voltage_v
        residual = compute_residual(q_in, q_out, q_branch, apply_bias=True)

        detector_results = self.detector_manager.process_sample(
            ts, q_in, q_out, q_branch, current_ma, bus_v,
            vibration=vibration, pump_on=pump_on,
        )

        # Adjudicate the flow reading BEFORE fusing. The flow detectors are not
        # independent of one another, so their agreement cannot establish that
        # the measurement they share is real — only the current and acoustic
        # channels can speak to that.
        plausibility = self.plausibility_guard.evaluate(
            residual, detector_results, pump_on=pump_on, q_in=q_in)

        fusion_result = self.fusion_engine.fuse(detector_results, plausibility=plausibility)

        persistence_sec = (ts - self.alarm_onset_ts) if self.alarm_onset_ts is not None else 0
        confidence_tier = ConfidenceEngine.evaluate(
            fusion_result["fused_score"],
            len(fusion_result["active_methods"]),
            persistence_sec=persistence_sec,
        )
        if fusion_result["suppressed_as_implausible"]:
            # The score stays on the record, but it must not be presented as
            # leak confidence when the reading behind it is not believed.
            confidence_tier = "NONE"

        state_result = self.state_machine.update(fusion_result["is_alarm"], residual)

        if state_result["is_confirmed"]:
            if self.alarm_onset_ts is None:
                self.alarm_onset_ts = ts
            localization = self.localization_service.localize_leak(residual, q_branch, servo_state_deg)
        else:
            self.alarm_onset_ts = None
            self.localization_service.observe_baseline(q_branch)
            localization = {"zone": "NONE", "confidence": "NONE"}

        topology = describe_topology()
        return {
            "ts": ts,
            "residual": round(residual, 3),
            "detectors": detector_results,
            "fusion": fusion_result,
            "confidence_tier": confidence_tier,
            "state": state_result,
            "localization": localization,
            "alarm_onset_ts": self.alarm_onset_ts,
            "plausibility": plausibility,
            "water_c": water_c,
            "hydraulics": {
                "topology": "metered_outflow" if topology["subtract_branch"] else "recombined_branch",
                "zero_leak_bias_lpm": topology["bias_lpm"],
                "branch_in_mass_balance": topology["subtract_branch"],
                "formula": topology["formula"],
            },
        }
