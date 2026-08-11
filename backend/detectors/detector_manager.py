"""Detector Manager — the five detection channels.

    1. mass_balance       |R| beyond k*sigma, sustained
    2. current_signature  pump current vs a fitted expected-current model
    3. mnf                residual during a scripted low-demand window
    4. cusum              change-point on R — catches slow leaks that never
                          cross the instantaneous threshold
    5. acoustic           50-150 Hz band energy vs a clean running baseline

Only two of these are independent of the flow meters. `mass_balance`, `cusum`
and `mnf` are three statistics of the same residual, so their agreement is one
measurement counted three times. `current_signature` and `acoustic` measure
different physics with different hardware — which is why fusion weights
cross-channel agreement more heavily than magnitude on any single detector, and
why the plausibility guard consults exactly those two.

There is no pressure channel. This rig has no transducer, and a flow-derived
"pressure" would be the mass balance signal wearing a disguise.
"""
from backend.detectors.acoustic_detector import AcousticDetector
from backend.detectors.current_signature_detector import CurrentSignatureDetector
from backend.detectors.cusum_detector import CUSUMDetector
from backend.detectors.mass_balance import MassBalanceDetector
from backend.detectors.mnf_detector import MNFDetector
from backend.detectors.residual import compute_residual
from backend.config.config_loader import thresholds_loader


class DetectorManager:
    def __init__(self):
        self.mass_balance_detector = MassBalanceDetector(
            sigma_threshold=thresholds_loader.get("mass_balance.sigma_threshold", 3.0),
            persistence_count=thresholds_loader.get("mass_balance.persistence_seconds", 5),
            apply_bias=True,
        )
        self.current_detector = CurrentSignatureDetector(
            baseline_ma=thresholds_loader.get("current_signature.baseline_ma", 420.0),
            current_drop_threshold_ma=thresholds_loader.get("current_signature.drop_threshold_ma", 25.0)
        )
        self.cusum_detector = CUSUMDetector(
            slack_k=thresholds_loader.get("cusum.k_allowance", 0.15),
            decision_h=thresholds_loader.get("cusum.h_decision_threshold", 5.0)
        )
        self.mnf_detector = MNFDetector(
            night_window_start=thresholds_loader.get("mnf.night_window_start", "01:00"),
            night_window_end=thresholds_loader.get("mnf.night_window_end", "05:00"),
            max_allowed_residual_lpm=thresholds_loader.get("mnf.max_allowed_residual_lpm", 0.15)
        )
        self.acoustic_detector = AcousticDetector()

    def process_sample(self, ts, q_in, q_out, q_branch, current_ma, bus_v=12.0,
                       vibration=None, pump_on=True):
        residual = compute_residual(q_in, q_out, q_branch, apply_bias=True)

        mb_res = self.mass_balance_detector.process_sample(q_in, q_out, q_branch)
        mb_res["method"] = "mass_balance"

        curr_res = self.current_detector.analyze(current_ma, q_in, bus_v)
        cusum_res = self.cusum_detector.analyze(residual)
        mnf_res = self.mnf_detector.analyze(ts, residual)
        acoustic_res = self.acoustic_detector.process_sample(vibration, pump_on)

        return [mb_res, curr_res, cusum_res, mnf_res, acoustic_res]
