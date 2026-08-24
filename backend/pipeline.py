"""Shared Detection Pipeline

The single code path every sample runs through, in both operating modes — same
detectors, same fusion, same plausibility guard, same localization, same response
shaping. Switching modes changes where data comes from, never how it is judged.
"""
import math

from backend.config.config_loader import thresholds_loader
from backend.detectors.detection_state_machine import DetectionStateMachine
from backend.detectors.detector_manager import DetectorManager
from backend.detectors.plausibility import PlausibilityGuard
from backend.detectors.residual import compute_residual, describe_topology
from backend.fusion.confidence_engine import ConfidenceEngine
from backend.fusion.fusion_engine import FusionEngine
from backend.localization.localization_service import LocalizationService
from backend.mode import get_active_mode
from backend.models.telemetry import TelemetryDTO


class DetectionPipeline:
    def __init__(self, mode: str = None):
        # The channel set is mode-dependent (6 live, 7 mock). Captured at
        # construction and reset on every mode switch, so a pipeline never
        # carries one mode's detectors into the other.
        self.mode = mode or get_active_mode()
        self.detector_manager = DetectorManager(mode=self.mode)
        self.fusion_engine = FusionEngine()
        self.localization_service = LocalizationService()
        persistence_s = float(thresholds_loader.get("detection.persistence_s", 10))
        recovery_s = float(thresholds_loader.get("detection.recovery_s", 5))
        interval_s = self.detector_manager.sample_interval_seconds
        self.state_machine = DetectionStateMachine(
            persistence_samples=max(1, math.ceil(persistence_s / interval_s)),
            recovery_samples=max(1, math.ceil(recovery_s / interval_s)),
        )
        self.plausibility_guard = PlausibilityGuard()
        self.alarm_onset_ts = None
        #: When each channel first crossed its own threshold during the CURRENT
        #: episode, cleared when everything falls quiet. Kept here rather than in
        #: each detector because only the pipeline sees `ts`, and computed
        #: server-side so a dashboard opened mid-leak still shows the sequence
        #: rather than starting its own clock.
        self.channel_crossed_at = {}

    def process_sample(self, sample: TelemetryDTO):
        """Evaluate one canonical sample.

        Wire-format compatibility belongs to the telemetry adapters.  Keeping a
        single DTO argument prevents mock/live callers from silently disagreeing
        about names such as ``voltage_v`` and ``bus_v``.
        """
        ts = sample.ts
        q_in = sample.flow.q_in_lpm
        q_out = sample.flow.q_out_lpm
        q_branch = sample.flow.q_branch_lpm
        current_ma = sample.power.current_ma
        bus_v = sample.power.bus_v
        pump_on = sample.actuators.pump1
        servo_state_deg = sample.actuators.servo_deg
        vibration = sample.vibration
        water_c = sample.temp.water_c
        pump1 = sample.actuators.pump1
        pump2 = sample.actuators.pump2
        # Explicitly simulated and mock-only. Live DTOs always carry None.
        pressure_bar = sample.pressure.bar if sample.pressure else None
        residual = compute_residual(q_in, q_out, q_branch, apply_bias=True)

        detector_results = self.detector_manager.process_sample(
            ts, q_in, q_out, q_branch, current_ma, bus_v,
            vibration=vibration, pump_on=pump_on, water_c=water_c,
            pump1=pump1, pump2=pump2,
            # Only ever non-None in mock. A live DetectorManager builds no
            # pressure detector, so this argument goes nowhere there.
            pressure_bar=pressure_bar,
        )

        # Record the ignition order. Different physics respond at different
        # speeds — flow imbalance is near-instant, acoustics need the jet to
        # establish, CUSUM integrates — so the sequence is itself evidence that
        # independent channels reached the same conclusion.
        alarming = {r.get("method") for r in detector_results if r.get("is_alarm")}
        for method in alarming:
            self.channel_crossed_at.setdefault(method, ts)
        if not alarming:
            self.channel_crossed_at.clear()
        else:
            for method in list(self.channel_crossed_at):
                if method not in alarming:
                    del self.channel_crossed_at[method]

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
            "mode": self.mode,
            "channels": self.detector_manager.methods(),
            #: {method: ts} for the current episode — the "moment of detection"
            #: sequence. Empty when nothing is alarming.
            "channel_crossed_at": dict(self.channel_crossed_at),
            "hydraulics": {
                "topology": "metered_outflow" if topology["subtract_branch"] else "recombined_branch",
                "zero_leak_bias_lpm": topology["bias_lpm"],
                "branch_in_mass_balance": topology["subtract_branch"],
                "formula": topology["formula"],
            },
        }
