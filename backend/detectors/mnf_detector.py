"""Minimum Night Flow (MNF) Detector

Tracks residual flow (Q_in - Q_out - Q_branch) during the configured overnight
quiet window, when legitimate demand should be near zero. A residual that
persists above `max_allowed_residual_lpm` during that window is a strong leak
signal because it can't be explained by normal daytime usage variability.
"""
from datetime import datetime, time as dtime


def _parse_hhmm(value: str) -> dtime:
    hh, mm = value.split(":")
    return dtime(int(hh), int(mm))


class MNFDetector:
    def __init__(self, night_window_start="01:00", night_window_end="05:00",
                 max_allowed_residual_lpm=0.15, persistence_count=5):
        self.window_start = _parse_hhmm(night_window_start)
        self.window_end = _parse_hhmm(night_window_end)
        self.max_allowed_residual_lpm = max_allowed_residual_lpm
        self.persistence_count = persistence_count
        self.baseline_samples = []
        self.consecutive_triggers = 0

    def _in_night_window(self, ts: float) -> bool:
        clock = datetime.fromtimestamp(ts).time()
        if self.window_start <= self.window_end:
            return self.window_start <= clock <= self.window_end
        # window wraps past midnight (e.g. 23:00 -> 04:00)
        return clock >= self.window_start or clock <= self.window_end

    def analyze(self, ts: float, residual_lpm: float):
        in_window = self._in_night_window(ts)

        if not in_window:
            # Outside the quiet window, MNF has nothing to say — normal demand
            # variability makes the residual meaningless as a leak signal.
            return {
                "method": "mnf",
                "in_night_window": False,
                "residual": round(residual_lpm, 3),
                "baseline_lpm": self._baseline(),
                "is_alarm": False,
                "confidence": 0.0
            }

        self.baseline_samples.append(residual_lpm)
        if len(self.baseline_samples) > 300:
            self.baseline_samples.pop(0)

        is_anomaly = residual_lpm > self.max_allowed_residual_lpm
        if is_anomaly:
            # Capped, for the same reason MassBalanceDetector caps its counter.
            # Unbounded, this counter reaches the length of the leak, and since a
            # clean sample only decrements it by one, recovery then takes as many
            # samples as the leak lasted: a 160-second night leak kept MNF
            # latched in alarm for 156 seconds after the residual returned to
            # normal. The fix was applied to mass balance but never carried
            # across to this detector.
            self.consecutive_triggers = min(self.persistence_count,
                                            self.consecutive_triggers + 1)
        else:
            self.consecutive_triggers = max(0, self.consecutive_triggers - 1)

        is_alarm = self.consecutive_triggers >= self.persistence_count
        confidence = min(1.0, residual_lpm / (self.max_allowed_residual_lpm * 3.0)) if is_anomaly else 0.0

        return {
            "method": "mnf",
            "in_night_window": True,
            "residual": round(residual_lpm, 3),
            "baseline_lpm": self._baseline(),
            "threshold_lpm": self.max_allowed_residual_lpm,
            "is_alarm": is_alarm,
            "confidence": round(confidence, 2)
        }

    def _baseline(self):
        if not self.baseline_samples:
            return 0.0
        return round(sum(self.baseline_samples) / len(self.baseline_samples), 3)
