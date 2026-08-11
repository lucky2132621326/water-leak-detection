"""Acoustic feature computation — the ONE definition, shared by training and runtime.

Both `scripts/export_acoustic_training.py` (which builds the CSV a model is
trained from) and `backend/detectors/acoustic_ml_detector.py` (which scores live
samples) import from here. Two implementations that "agree today" is how a model
ends up being scored on inputs it never saw, and the failure is silent: the
classifier returns a confident probability computed from a feature vector that
means something different than it did in training.

Why the features look like this
-------------------------------
Absolute band energies are meaningless across rigs. They depend on how tight the
sensor is zip-tied, where on the pipe it sits, and how hard the pump is working.
A model trained on absolute energies learns one particular mounting.

So every energy feature is a **ratio to that rig's own quiet baseline at the
current pump duty**. Duty keying matters specifically because P2 cycles demand:
without it, the baseline drifts across duty states and `ratio_mid` / `ratio_rms`
inherit that drift as a phantom signal.

`spectral_tilt = band_mid / band_low` needs no baseline at all. Two bands, same
sensor, same instant — mounting quality and pump duty divide out by construction.
That self-normalisation is why it is the most robust feature in the set and the
one least damaged by a stale baseline.

A note on `piezo_centroid_hz`
-----------------------------
It is NOT a spectral centroid. The firmware computes a slope-weighted
zero-crossing proxy (`vibration_sensor.cpp::readPiezo`), which tracks frequency
content monotonically but is not calibrated in Hz. It is a legitimate feature —
the model only needs it to move with the physics — but the number must never be
read, plotted, or reported as a literal frequency.
"""
from typing import Optional

#: Feature names in the order the bundle expects. The bundle carries its own
#: `features` list and THAT is authoritative — this is the fallback for a bundle
#: that omits it, and the order both paths default to.
DEFAULT_FEATURE_ORDER = (
    "ratio_mid",
    "ratio_low",
    "ratio_high",
    "ratio_rms",
    "spectral_tilt",
    "piezo_rms",
    "piezo_centroid_hz",
    "water_c",
)

#: Baseline dict keys, matching the exported bundle's structure exactly. Do not
#: rename: a bundle trained in Colab is keyed with these strings and the runtime
#: must index it identically.
BASELINE_KEYS = {
    "band_low": "band_low_base",
    "band_mid": "band_mid_base",
    "band_high": "band_high_base",
    "rms": "rms_base",
}

#: Guard against divide-by-zero on a silent or dead channel. A baseline this
#: small means the rig was not actually running when it was measured.
_MIN_BASELINE = 1e-9


class FeatureUnavailable(Exception):
    """A required input was missing, so no feature vector can be built.

    Raised rather than returning a filled-in default: substituting a plausible
    number for an absent sensor is exactly how fabricated data reaches a model.
    The detector catches this and reports UNAVAILABLE.
    """


def resolve_pump_duty(available_duties, pump1: bool = True, pump2: bool = False,
                      q_in_lpm: Optional[float] = None,
                      nominal_flow_lpm: float = 5.2) -> float:
    """Pick the baseline duty bucket this sample belongs to.

    The baseline is a small set of discrete duty levels (the exported bundle has
    0.6 / 0.8 / 1.0), so a continuous estimate is snapped to the nearest one.

    Duty is estimated from measured inlet flow relative to the rig's nominal
    full-flow rate, because that is observable in both live and mock telemetry
    and in a stored training row. Pump *state* alone would only distinguish two
    or three cases and could not tell a throttled P1 from a full-open one.

    IMPORTANT: this definition must match whatever the training notebook used to
    bucket its baseline. If Colab bucketed duty differently, every ratio feature
    is divided by the wrong number and the model is scored on inputs it never
    saw. There is no way to detect that from the bundle alone — the duty
    definition is not stored in it.
    """
    duties = sorted(float(d) for d in available_duties)
    if not duties:
        raise FeatureUnavailable("baseline carries no duty levels")

    if q_in_lpm is None or nominal_flow_lpm <= 0:
        # No flow reading: fall back to pump state. P1 alone is the rig's normal
        # supply condition, so it maps to the highest bucket; both pumps running
        # is the same supply with extra demand, which does not raise P1's duty.
        estimated = 1.0 if pump1 else duties[0]
    else:
        estimated = float(q_in_lpm) / float(nominal_flow_lpm)

    return min(duties, key=lambda d: abs(d - estimated))


def _baseline_at(baseline: dict, band_key: str, duty: float) -> float:
    """Read one band's baseline at `duty`, tolerating str-or-float dict keys.

    JSON round-tripping turns float keys into strings, so a bundle written by one
    path and read by another can carry either. Both are accepted rather than
    guessed at.
    """
    table = baseline.get(BASELINE_KEYS[band_key])
    if not table:
        raise FeatureUnavailable(f"baseline has no '{BASELINE_KEYS[band_key]}' table")

    for candidate in (duty, str(duty), f"{duty:.1f}", int(duty) if duty == int(duty) else None):
        if candidate is not None and candidate in table:
            return float(table[candidate])

    # Nearest available, so a duty bucket the bundle never saw degrades to the
    # closest one it did rather than failing the whole sample.
    try:
        nearest = min(table.keys(), key=lambda k: abs(float(k) - duty))
    except (TypeError, ValueError):
        raise FeatureUnavailable(f"baseline table for {band_key} has unusable keys")
    return float(table[nearest])


def compute_features(band_low, band_mid, band_high, rms,
                     piezo_rms, piezo_centroid_hz, water_c,
                     baseline: dict, pump_duty: float) -> dict:
    """Build the feature dict for one sample.

    Every argument is required. `None` for any of them raises
    `FeatureUnavailable` — the model has no notion of a missing input, and
    filling one in would be inventing a measurement.
    """
    missing = [name for name, value in (
        ("band_low", band_low), ("band_mid", band_mid), ("band_high", band_high),
        ("rms", rms), ("piezo_rms", piezo_rms),
        ("piezo_centroid_hz", piezo_centroid_hz), ("water_c", water_c),
    ) if value is None]
    if missing:
        raise FeatureUnavailable(f"missing required inputs: {', '.join(missing)}")

    if not baseline:
        raise FeatureUnavailable("no baseline available")

    base_low = max(_baseline_at(baseline, "band_low", pump_duty), _MIN_BASELINE)
    base_mid = max(_baseline_at(baseline, "band_mid", pump_duty), _MIN_BASELINE)
    base_high = max(_baseline_at(baseline, "band_high", pump_duty), _MIN_BASELINE)
    base_rms = max(_baseline_at(baseline, "rms", pump_duty), _MIN_BASELINE)

    return {
        "ratio_mid": float(band_mid) / base_mid,
        "ratio_low": float(band_low) / base_low,
        "ratio_high": float(band_high) / base_high,
        "ratio_rms": float(rms) / base_rms,
        # Self-normalising: no baseline, so a stale or wrongly-bucketed baseline
        # cannot corrupt this one.
        "spectral_tilt": float(band_mid) / max(float(band_low), _MIN_BASELINE),
        "piezo_rms": float(piezo_rms),
        # Slope-weighted zero-crossing proxy, not calibrated Hz — see module docstring.
        "piezo_centroid_hz": float(piezo_centroid_hz),
        "water_c": float(water_c),
    }


def to_vector(features: dict, feature_order) -> list:
    """Order the feature dict to match the bundle's own `features` list.

    Ordering by the bundle rather than by our constant is the point: a model
    retrained with a different feature order must not be silently fed the old
    one. scikit-learn accepts any float vector of the right length, so a
    mismatch produces plausible predictions instead of an error.
    """
    try:
        return [float(features[name]) for name in feature_order]
    except KeyError as e:
        raise FeatureUnavailable(f"bundle expects feature {e} which this build does not compute")


def features_from_sample(vibration, water_c, baseline, pump_duty) -> dict:
    """Convenience wrapper for a runtime `VibrationData` object."""
    if vibration is None or not getattr(vibration, "has_accelerometer", False):
        raise FeatureUnavailable("no accelerometer data in this sample")

    return compute_features(
        band_low=vibration.band_low,
        band_mid=vibration.band_mid,
        band_high=vibration.band_high,
        rms=vibration.rms,
        piezo_rms=vibration.piezo_rms,
        piezo_centroid_hz=vibration.piezo_centroid_hz,
        water_c=water_c,
        baseline=baseline,
        pump_duty=pump_duty,
    )
