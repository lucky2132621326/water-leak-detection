"""Acoustic Leak Detector (MPU6050 + piezo)

Hardware spec v2, section 6, channel 5. Band energies are meaningless in
absolute terms — a leak jet's energy concentrates in the 50-150 Hz "mid"
band, but what counts as "elevated" depends on pump duty, mounting, and pipe
material. So this detects on the RATIO of live band_mid to a stored clean
baseline, not a raw threshold, exactly like the spec requires.

If no vibration data arrives (sensor not yet wired, or a replay run recorded
before the acoustic channel existed), this reports itself as unavailable
rather than fabricating an alarm/no-alarm verdict — the fusion engine and
UI both need to treat "no signal" differently from "signal says normal."
"""


class AcousticDetector:
    def __init__(self, baseline_band_mid, ratio_threshold=1.8, persistence_count=3):
        self.baseline_band_mid = max(float(baseline_band_mid), 1e-6)
        self.ratio_threshold = ratio_threshold
        self.persistence_count = persistence_count
        self.consecutive_triggers = 0

    def analyze(self, vibration: dict = None):
        if not vibration or vibration.get("band_mid") is None:
            return {
                "method": "acoustic",
                "available": False,
                "is_alarm": False,
                "confidence": 0.0,
            }

        band_mid = float(vibration["band_mid"])
        ratio = band_mid / self.baseline_band_mid
        is_anomaly = ratio >= self.ratio_threshold

        if is_anomaly:
            self.consecutive_triggers += 1
        else:
            self.consecutive_triggers = max(0, self.consecutive_triggers - 1)

        is_alarm = self.consecutive_triggers >= self.persistence_count
        confidence = min(1.0, (ratio - 1.0) / max(self.ratio_threshold - 1.0, 0.01)) if is_anomaly else 0.0

        return {
            "method": "acoustic",
            "available": True,
            "band_mid": round(band_mid, 4),
            "baseline_band_mid": round(self.baseline_band_mid, 4),
            "ratio_to_baseline": round(ratio, 2),
            "piezo_rms": vibration.get("piezo_rms"),
            "piezo_centroid_hz": vibration.get("piezo_centroid_hz"),
            "is_anomaly": is_anomaly,
            "is_alarm": is_alarm,
            "confidence": round(confidence, 2),
        }
