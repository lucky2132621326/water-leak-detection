"""Acoustic Leak Detector — MPU6050 band energy, with the piezo as corroboration.

Water forced through a small orifice at pressure jets rather than flows, and that
jet excites the pipe wall broadband. For a rig this size the leak energy sits
mostly in **50-150 Hz** (`band_mid`), which is why the firmware reports that band
separately.

Why this is a ratio, never an absolute
--------------------------------------
The MPU6050 is bolted to a pipe carrying a running pump. Absolute band energies
are dominated by pump vibration, and they change with pump duty, mounting torque,
water temperature and where on the pipe the sensor ended up. No fixed threshold
can survive any of that. The detector therefore works on the **ratio to this
rig's own clean baseline at the current pump duty** — spec Part D.7.

Why this channel is worth having
--------------------------------
It is *physically independent of the flow meters*. Both flow meters could drift
together, ice up, or drop out entirely without moving the acoustic signature at
all. That independence is what makes it useful twice over: as a detector, and as
the corroborating channel that lets `PlausibilityGuard` tell a dead flow meter
from a real burst — a dropped meter makes no sound, while a real leak jets
audibly.

The piezo is optional
---------------------
`piezo_rms` / `piezo_centroid_hz` are None when no disc is fitted. The
accelerometer carries the channel alone in that case; the piezo only adds
corroboration at frequencies the MPU6050 cannot reach. A missing piezo must
never disable acoustic detection, so it is treated as extra evidence, never as a
requirement.
"""
from collections import deque

from backend.config.config_loader import thresholds_loader
from backend.utils.logger import logger


class AcousticDetector:
    def __init__(self, ratio_threshold=None, persistence_count=None,
                 warmup_samples=None, baseline_alpha=None, min_baseline_energy=None):
        def cfg(explicit, key, default):
            return float(explicit if explicit is not None
                         else thresholds_loader.get(f"acoustic.{key}", default))

        #: band_mid must exceed this multiple of the clean baseline to count.
        self.ratio_threshold = cfg(ratio_threshold, "vib_ratio_threshold", 1.8)
        self.persistence_count = int(cfg(persistence_count, "persistence_samples", 5))
        self.warmup_samples = int(cfg(warmup_samples, "warmup_samples", 20))
        self.baseline_alpha = cfg(baseline_alpha, "baseline_alpha", 0.02)
        #: Below this the rig is effectively silent (pump off, or a sensor
        #: reading zero). Ratios against a near-zero baseline explode, so the
        #: detector stands down rather than producing an enormous meaningless
        #: multiple.
        self.min_baseline_energy = cfg(min_baseline_energy, "min_baseline_energy", 1e-4)

        self.baseline = None
        self.window = deque(maxlen=100)
        self.consecutive = 0
        self.samples_seen = 0

    def reset(self):
        self.baseline = None
        self.window.clear()
        self.consecutive = 0
        self.samples_seen = 0

    def process_sample(self, vibration, pump_on=True):
        """`vibration` is a VibrationData, or None when the rig has no MPU6050."""
        result = {
            "method": "acoustic",
            "is_alarm": False,
            "confidence": 0.0,
            "band_mid": None,
            "baseline_band_mid": round(self.baseline, 6) if self.baseline is not None else None,
            "ratio": None,
            "ratio_threshold": self.ratio_threshold,
            "piezo_corroborates": None,
            "active": False,
        }

        if vibration is None or not getattr(vibration, "has_accelerometer", True):
            # No MPU6050 fitted. Inactive rather than silent-and-passing, so
            # fusion redistributes this weight instead of scoring the rig as if
            # the pipe had been listened to and found quiet.
            result["reason"] = "no accelerometer fitted — detector inactive"
            return result

        if not pump_on:
            # No pump, no flow, no jet. Silence here is expected and says nothing
            # about whether a leak path is open.
            self.consecutive = 0
            result["reason"] = "pump off — no hydraulic noise to compare against"
            return result

        band_mid = float(vibration.band_mid or 0.0)
        result["active"] = True
        result["band_mid"] = round(band_mid, 6)
        self.samples_seen += 1

        if self.baseline is None:
            self.baseline = max(band_mid, self.min_baseline_energy)
            self.window.append(band_mid)
            result["reason"] = "establishing clean baseline"
            return result

        if self.baseline < self.min_baseline_energy:
            result["reason"] = "baseline energy too low to form a meaningful ratio"
            return result

        ratio = band_mid / self.baseline
        result["ratio"] = round(ratio, 3)
        result["baseline_band_mid"] = round(self.baseline, 6)

        if self.samples_seen < self.warmup_samples:
            self._track(band_mid, anomalous=False)
            result["reason"] = f"warming up ({self.samples_seen}/{self.warmup_samples})"
            return result

        anomalous = ratio >= self.ratio_threshold
        self.consecutive = self.consecutive + 1 if anomalous else 0
        self._track(band_mid, anomalous=anomalous)

        # The piezo reaches higher frequencies than the MPU6050, so agreement
        # between them is genuine corroboration rather than the same measurement
        # twice. Optional: absent means "no opinion", never "disagrees".
        result["piezo_corroborates"] = self._piezo_agrees(vibration, anomalous)

        if anomalous and self.consecutive >= self.persistence_count:
            result["is_alarm"] = True
            # Saturates at twice the threshold ratio: beyond that the channel is
            # certain and further energy adds no information.
            span = max(self.ratio_threshold, 1e-6)
            confidence = min(1.0, (ratio - self.ratio_threshold) / span + 0.5)
            if result["piezo_corroborates"]:
                confidence = min(1.0, confidence + 0.1)
            result["confidence"] = round(confidence, 3)
            # Rising edge only. Logging every sample of a sustained leak buries
            # the transition that actually matters under hundreds of identical
            # lines, which is what makes a log unreadable during bring-up.
            if self.consecutive == self.persistence_count:
                logger.warning(
                    f"[Acoustic] band_mid {band_mid:.5f} is {ratio:.2f}x the clean baseline "
                    f"{self.baseline:.5f} — sustained {self.consecutive} samples")

        return result

    def _piezo_agrees(self, vibration, anomalous: bool):
        """None when no piezo is fitted — absence is not disagreement."""
        if not vibration.has_piezo:
            return None
        if not anomalous:
            return False
        centroid = vibration.piezo_centroid_hz
        # A leak jet pushes the piezo's spectral centroid up as well as its
        # amplitude; a pump-duty change moves amplitude alone.
        return bool(centroid is not None and centroid >= 100.0)

    def _track(self, band_mid: float, anomalous: bool):
        """Only quiet samples update the baseline.

        Letting leak samples drag the baseline up would make the detector adapt
        to the leak and fall silent — the exact failure already found and fixed
        in the mass balance detector, where a sustained leak raised its own
        threshold until the alarm died.
        """
        if anomalous:
            return
        self.window.append(band_mid)
        self.baseline = (self.baseline_alpha * band_mid
                         + (1 - self.baseline_alpha) * self.baseline)
