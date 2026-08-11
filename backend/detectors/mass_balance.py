"""Mass Balance Leak Detector

Calculates flow differential residual Delta Q = Q_in - (Q_out + Q_branch)
and evaluates 3-sigma dynamic thresholding.
"""

import numpy as np

from backend.config.config_loader import thresholds_loader
from backend.detectors.residual import compute_residual


class MassBalanceDetector:
    def __init__(self, sigma_threshold=3.0, persistence_count=5, calibrated_sigma=None):
        self.sigma_threshold = sigma_threshold
        self.persistence_count = persistence_count
        #: Sigma from the zero-leak calibration run. Used as the floor until the
        #: rolling window has warmed up, so a fresh detector uses the rig's
        #: measured noise rather than a guessed constant.
        self.calibrated_sigma = float(
            calibrated_sigma if calibrated_sigma is not None
            else thresholds_loader.get("calibration.sigma_lpm", 0.05))
        self.history = []
        self.consecutive_triggers = 0

    def process_sample(self, q_in, q_out, q_branch=0.0):
        # Topology-aware and bias-corrected — see backend/detectors/residual.py.
        residual = compute_residual(q_in, q_out, q_branch)

        # np.mean/np.std return numpy.float64; comparing against them yields
        # numpy.bool_, which json/FastAPI can't serialize (silently breaks the
        # API response) — cast everything back to native Python types here.
        warm = len(self.history) >= 10
        mean = float(np.mean(self.history)) if warm else 0.0
        std = float(np.std(self.history)) if warm else self.calibrated_sigma
        # Floor at 4x the calibrated sigma so a freakishly quiet window cannot
        # drive the threshold below the rig's known noise level.
        threshold = mean + max(self.sigma_threshold * std, 4 * self.calibrated_sigma)

        is_anomaly = bool(abs(residual) > threshold)

        # Only quiet samples define "normal". Admitting anomalous ones lets a
        # sustained leak pull its own baseline up until the threshold overtakes
        # the residual and the alarm dies — detection by amnesia.
        #
        # Found by the small_leak mock scenario: a 0.3 L/min leak tripped at
        # t=122 (residual 0.344 > threshold 0.223), then the window absorbed it
        # and by t=160 the threshold had climbed to 0.573 against an unchanged
        # 0.30 residual. It never reached the 5-sample persistence requirement,
        # so the leak was reported as clean. Large leaks survived only because
        # they trip persistence before the window can adapt.
        if not is_anomaly or not warm:
            self.history.append(residual)
            if len(self.history) > 100:
                self.history.pop(0)
        if is_anomaly:
            # Capped. Left unbounded, a long leak drives the counter to the
            # length of the leak, and since a clean sample only decrements it by
            # one, recovery then takes as many samples as the leak lasted — a
            # 2-minute leak kept the detector latched for 2 minutes after the
            # valve shut. Found by the small_leak scenario, where every false
            # positive sat after the leak had already closed.
            self.consecutive_triggers = min(self.persistence_count, self.consecutive_triggers + 1)
        else:
            self.consecutive_triggers = max(0, self.consecutive_triggers - 1)

        is_alarm = bool(self.consecutive_triggers >= self.persistence_count)
        confidence = min(1.0, abs(residual) / (threshold + 0.01)) if is_anomaly else 0.0

        return {
            "method": "Mass_Balance",
            "residual": round(residual, 3),
            "threshold": round(threshold, 3),
            "is_anomaly": is_anomaly,
            "is_alarm": is_alarm,
            "confidence": round(confidence, 2)
        }
