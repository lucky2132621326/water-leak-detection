"""SIMULATED Pressure Drop Detector — MOCK MODE ONLY.

=============================================================================
EVERY NUMBER THIS MODULE TOUCHES IS GENERATED. NOTHING HERE IS MEASURED.
=============================================================================

The physical rig has no pressure transducer, and would not benefit from a cheap
one: a 12V diaphragm pump develops well under 1 bar, while affordable
transducers are ranged 0-12 bar. A real leak's pressure signature would sit
beneath the sensor's own noise floor — you would be reading quantisation error.

This channel therefore exists to demonstrate how the system extends to pressure
instrumentation on a rig that has it. It runs against generated pressure from
the mock scenario and is labelled SIMULATED at every level: in the detector
result, in the alert evidence, and on the dashboard.

Why the labelling is the important part
---------------------------------------
Before this rewrite the UI printed "pressure 2.38 bar (measured)" and "pressure
trending down to 2.04 bar (estimated)". Neither was true. "measured" asserts a
sensor reading that does not exist, and "estimated" implies derivation from
something observed when the number came from a random generator. Presenting a
fabricated value as instrument output is the most damaging thing a monitoring
system can do — everything else it reports becomes unfalsifiable.

So this module never emits the words "measured" or "estimated". Only SIMULATED.

`backend/detectors/detector_manager.py` constructs this class only when the mode
is mock, and imports it lazily inside that branch — a live-mode process never
loads this file at all.
"""
from collections import deque

from backend.config.config_loader import thresholds_loader
from backend.utils.logger import logger

#: Attached to every result and rendered wherever pressure appears. One string,
#: one place to change it.
SIMULATED_BADGE = (
    "Pressure channel is SIMULATED — demonstrates system extension to pressure "
    "instrumentation. The physical rig has no pressure sensor."
)
SIMULATED_SOURCE = "simulated"


class SimulatedPressureDetector:
    METHOD = "pressure_drop"

    def __init__(self, min_drop_bar=None, sigma_multiplier=None,
                 persistence_count=None, warmup_samples=None, baseline_alpha=None):
        def cfg(explicit, key, default):
            return float(explicit if explicit is not None
                         else thresholds_loader.get(f"pressure_drop.{key}", default))

        self.min_drop_bar = cfg(min_drop_bar, "min_drop_bar", 0.15)
        self.sigma_multiplier = cfg(sigma_multiplier, "sigma_multiplier", 3.0)
        self.persistence_count = int(cfg(persistence_count, "persistence_samples", 5))
        self.warmup_samples = int(cfg(warmup_samples, "warmup_samples", 20))
        self.baseline_alpha = cfg(baseline_alpha, "baseline_alpha", 0.02)

        self.baseline = None
        self.window = deque(maxlen=100)
        self.consecutive = 0
        self.samples_seen = 0

    def reset(self):
        self.baseline = None
        self.window.clear()
        self.consecutive = 0
        self.samples_seen = 0

    def _std(self):
        if len(self.window) < 2:
            return 0.0
        mean = sum(self.window) / len(self.window)
        return (sum((v - mean) ** 2 for v in self.window) / (len(self.window) - 1)) ** 0.5

    def _result(self, **overrides) -> dict:
        base = {
            "method": self.METHOD,
            "is_alarm": False,
            "confidence": 0.0,
            "pressure_bar": None,
            "baseline_bar": round(self.baseline, 3) if self.baseline is not None else None,
            "drop_bar": 0.0,
            "threshold_bar": None,
            "active": False,
            # Never "measured", never "estimated". These three fields travel with
            # the result so no consumer can render a pressure without the caveat.
            "source": SIMULATED_SOURCE,
            "is_simulated": True,
            "simulated_notice": SIMULATED_BADGE,
            "reason": None,
        }
        base.update(overrides)
        return base

    def process_sample(self, pressure_bar, residual_lpm=0.0, pump_on=True) -> dict:
        if pressure_bar is None:
            return self._result(reason="no simulated pressure in this sample")

        if not pump_on:
            # Pressure legitimately collapses with the pump off; that is not a leak.
            self.consecutive = 0
            return self._result(pressure_bar=round(float(pressure_bar), 3),
                                reason="pump off — pressure drop expected, not evidence of a leak")

        pressure_bar = float(pressure_bar)
        self.samples_seen += 1
        result = self._result(active=True, pressure_bar=round(pressure_bar, 3))

        if self.baseline is None:
            self.baseline = pressure_bar
            self.window.append(pressure_bar)
            result["baseline_bar"] = round(self.baseline, 3)
            result["reason"] = "establishing SIMULATED baseline"
            return result

        drop = self.baseline - pressure_bar
        threshold = max(self.min_drop_bar, self.sigma_multiplier * self._std())
        result.update(drop_bar=round(drop, 3), threshold_bar=round(threshold, 3),
                      baseline_bar=round(self.baseline, 3))

        if self.samples_seen < self.warmup_samples:
            self._track(pressure_bar, anomalous=False)
            result["reason"] = f"warming up ({self.samples_seen}/{self.warmup_samples})"
            return result

        anomalous = drop > threshold
        self.consecutive = self.consecutive + 1 if anomalous else 0
        self._track(pressure_bar, anomalous=anomalous)

        if anomalous and self.consecutive >= self.persistence_count:
            span = max(threshold, 1e-6)
            result["is_alarm"] = True
            result["confidence"] = round(min(1.0, (drop - threshold) / span + 0.5), 3)
            if self.consecutive == self.persistence_count:
                logger.warning(
                    f"[SimulatedPressure] {drop:.3f} bar below baseline "
                    f"{self.baseline:.2f} — SIMULATED CHANNEL, mock mode only")

        return result

    def _track(self, pressure_bar: float, anomalous: bool):
        """Only quiet samples update the baseline and the noise window.

        Both exclusions matter. Letting a sustained leak drag the baseline down
        would make the detector adapt to the fault and fall silent. Admitting
        leak samples into the noise window is subtler and just as damaging: the
        window would hold both pre-leak and leaked pressures, its deviation would
        balloon, and the 3-sigma threshold would climb above the very drop it
        exists to catch.
        """
        if anomalous:
            return
        self.window.append(pressure_bar)
        self.baseline = (self.baseline_alpha * pressure_bar
                         + (1 - self.baseline_alpha) * self.baseline)
