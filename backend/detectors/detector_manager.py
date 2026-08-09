"""
Detector Manager
Orchestrates the four leak-detection signals the problem statement requires:
Mass Balance (3-sigma), Current Signature, Minimum Night Flow, and CUSUM.
"""
from backend.detectors.mass_balance import MassBalanceDetector
from backend.detectors.current_signature_detector import CurrentSignatureDetector
from backend.detectors.cusum_detector import CUSUMDetector
from backend.detectors.mnf_detector import MNFDetector
from backend.config.config_loader import thresholds_loader
from backend.calibration.calibration_repository import CalibrationRepository


class DetectorManager:
    def __init__(self):
        calibration = CalibrationRepository()
        self.mass_balance_detector = MassBalanceDetector(
            sigma_threshold=thresholds_loader.get("mass_balance.sigma_threshold", 3.0),
            persistence_count=thresholds_loader.get("mass_balance.persistence_seconds", 5),
            baseline_sigma=calibration.get_sigma(),
        )
        self.current_detector = CurrentSignatureDetector(
            baseline_ma=thresholds_loader.get("current_signature.baseline_ma", 420.0),
            current_drop_threshold_ma=thresholds_loader.get("current_signature.drop_threshold_ma", 25.0)
        )
        self.cusum_detector = CUSUMDetector(
            slack_k=thresholds_loader.get("cusum.k_allowance", 0.15),
            decision_h=thresholds_loader.get("cusum.h_decision_threshold", 3.0),
            reset_after_normal_samples=thresholds_loader.get("cusum.reset_after_normal_samples", 10),
        )
        self.mnf_detector = MNFDetector(
            night_window_start=thresholds_loader.get("mnf.night_window_start", "01:00"),
            night_window_end=thresholds_loader.get("mnf.night_window_end", "05:00"),
            max_allowed_residual_lpm=thresholds_loader.get("mnf.max_allowed_residual_lpm", 0.15)
        )

    def process_sample(self, ts, q_in, q_out, q_branch, current_ma, voltage_v=12.0,
                       balance_q_in=None, balance_q_branch=None):
        effective_q_in = q_in if balance_q_in is None else balance_q_in
        effective_q_branch = q_branch if balance_q_branch is None else balance_q_branch
        residual = effective_q_in - (q_out + effective_q_branch)

        mb_res = self.mass_balance_detector.process_sample(effective_q_in, q_out, effective_q_branch)
        mb_res["method"] = "mass_balance"

        curr_res = self.current_detector.analyze(current_ma, q_in, voltage_v)
        cusum_res = self.cusum_detector.analyze(residual)
        mnf_res = self.mnf_detector.analyze(ts, residual)

        return [mb_res, curr_res, cusum_res, mnf_res]
