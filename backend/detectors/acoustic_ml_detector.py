"""Acoustic ML Detector — a supervised classifier on vibration signatures.

Sits alongside the physics-based detectors as one more channel into fusion. It
implements the same interface as the rest, so fusion needs no special case.

What it adds over the rule-based `acoustic` detector
----------------------------------------------------
`AcousticDetector` asks one question: is band_mid louder than baseline by more
than a threshold? That catches a leak that is simply loud. It cannot use the
*shape* of the spectrum — that a leak raises band_mid disproportionately to
band_low, that the piezo centroid climbs while RMS rises, that a cavitation
burst looks different from a sustained jet. A classifier trained on labelled runs
can learn those joint patterns.

The honesty problem, and why it gates on a string
-------------------------------------------------
The bundle shipped today has `note == 'SYNTHETIC — not valid results'`. It was
trained on generated data, so what it learned is the mock generator's noise
model. Running it in mock mode is a genuine end-to-end integration proof. Running
it against a physical rig and reporting the probability as a leak likelihood
would be presenting a fabricated number as a measurement.

So: `enabled` defaults False, mock mode may enable it, and **live mode refuses
any bundle whose note is not exactly 'trained on physical ground truth'**. The
note is attached to every result so the UI cannot render a confidence without
also having the caveat.

Failure behaviour
-----------------
Every failure path reports UNAVAILABLE (`active: False`) and lets fusion
renormalise over the remaining channels. Missing bundle, corrupt bundle, sklearn
version mismatch, no accelerometer, null piezo, null water temperature, a
prediction that throws — none of them may take down the pipeline. A leak
detection system that stops detecting because a model file is bad has failed far
worse than one that carries on with five channels instead of six.
"""
from backend.config.config_loader import thresholds_loader
from backend.ml.acoustic_features import (
    FeatureUnavailable,
    features_from_sample,
    resolve_pump_duty,
    to_vector,
)
from backend.ml.bundle import BundleLoadError, load_bundle
from backend.mode import MODE_LIVE
from backend.utils.logger import logger


class AcousticMLDetector:
    METHOD = "acoustic_ml"

    def __init__(self, mode: str = None, bundle_path: str = None, enabled: bool = None,
                 probability_threshold: float = None, persistence_count: int = None,
                 nominal_flow_lpm: float = None):
        def cfg(explicit, key, default):
            return explicit if explicit is not None else thresholds_loader.get(f"acoustic_ml.{key}", default)

        self.mode = mode
        #: Defaults FALSE. An ML channel must be switched on deliberately, not
        #: inherited by anyone who pulls the repo.
        self.enabled = bool(cfg(enabled, "enabled", False))
        self.bundle_path = cfg(bundle_path, "bundle_path", "models/acoustic_clf-2.joblib")
        self.probability_threshold = float(cfg(probability_threshold, "probability_threshold", 0.7))
        #: Same persistence discipline as every other detector. A single noisy
        #: frame — a cavitation burst, a knock on the bench — must not fire it.
        self.persistence_count = int(cfg(persistence_count, "persistence_samples", 5))
        self.nominal_flow_lpm = float(cfg(nominal_flow_lpm, "nominal_flow_lpm", 5.2))

        self.bundle = None
        self.unavailable_reason = None
        self.consecutive = 0
        self._logged_unavailable = False
        #: EMA of the probability while the channel is NOT calling a leak — the
        #: model's own idea of "quiet". Reported so the UI can show the delta
        #: (0.08 -> 0.93) rather than a bare probability, which tells a reader
        #: nothing about how far it moved.
        self.baseline_probability = None

        self._initialise()

    # --- startup ----------------------------------------------------------
    def _initialise(self):
        if not self.enabled:
            self.unavailable_reason = "disabled by configuration (acoustic_ml.enabled = false)"
            return

        try:
            bundle = load_bundle(self.bundle_path)
        except BundleLoadError as e:
            # Loud, once, at startup — not per sample.
            self.unavailable_reason = f"bundle unavailable: {e}"
            logger.warning(f"[AcousticML] {self.unavailable_reason}")
            return

        # THE HONESTY GATE. A synthetic-trained model may demonstrate the
        # integration in mock mode; it may not produce numbers about a real rig.
        if self.mode == MODE_LIVE and not bundle.is_physical:
            self.unavailable_reason = (
                f"refused in live mode: bundle note is {bundle.note!r}. "
                f"A model trained on generated data describes the generator, not this "
                f"pipe. Retrain on logged physical runs and re-export with "
                f"note='trained on physical ground truth'.")
            logger.warning(f"[AcousticML] {self.unavailable_reason}")
            # Kept, not discarded: the UI still needs to show which bundle was
            # rejected and why.
            self.bundle = bundle
            return

        self.bundle = bundle

    @property
    def is_available(self) -> bool:
        return self.bundle is not None and self.unavailable_reason is None

    def reset(self):
        self.consecutive = 0
        self.baseline_probability = None

    # --- per-sample -------------------------------------------------------
    def _result(self, **overrides) -> dict:
        base = {
            "method": self.METHOD,
            "is_alarm": False,
            "confidence": 0.0,
            "active": False,
            "probability": None,
            "threshold": self.probability_threshold,
            "consecutive": self.consecutive,
            "pump_duty": None,
            "baseline_probability": (round(self.baseline_probability, 3)
                                     if self.baseline_probability is not None else None),
            "features": None,
            # Provenance rides on EVERY result, available or not, so no consumer
            # can display a probability without the caveat that qualifies it.
            "model_note": self.bundle.note if self.bundle else None,
            "is_synthetic_model": (not self.bundle.is_physical) if self.bundle else None,
            "sklearn_warning": self.bundle.sklearn_warning if self.bundle else None,
            "reason": None,
        }
        base.update(overrides)
        return base

    def process_sample(self, vibration, water_c=None, q_in_lpm=None,
                       pump1=True, pump2=False, pump_on=True) -> dict:
        if not self.is_available:
            return self._result(reason=self.unavailable_reason)

        if not pump_on:
            # No flow, no jet. Silence proves nothing, and the baseline was
            # measured with the pump running.
            self.consecutive = 0
            return self._result(reason="pump off — no acoustic baseline applies")

        try:
            duty = resolve_pump_duty(
                self.bundle.duty_levels, pump1=pump1, pump2=pump2,
                q_in_lpm=q_in_lpm, nominal_flow_lpm=self.nominal_flow_lpm)
            features = features_from_sample(
                vibration, water_c, self.bundle.baseline, duty)
            # Ordered by the BUNDLE's own list, not a local constant — a
            # retrained model with a different order must not be fed the old one.
            vector = to_vector(features, self.bundle.features)
        except FeatureUnavailable as e:
            self.consecutive = 0
            if not self._logged_unavailable:
                logger.info(f"[AcousticML] no feature vector this sample: {e}")
                self._logged_unavailable = True
            return self._result(reason=f"features unavailable: {e}")

        try:
            proba = self.bundle.model.predict_proba(self._as_model_input(vector))
            # Index by the model's own class list rather than assuming column 1
            # is the positive class.
            classes = list(getattr(self.bundle.model, "classes_", [0, 1]))
            leak_probability = float(proba[0][classes.index(1)]) if 1 in classes else float(proba[0][-1])
        except Exception as e:
            # A prediction failure disables the channel for good rather than
            # throwing once a second for the rest of the run.
            self.consecutive = 0
            self.unavailable_reason = f"prediction failed: {type(e).__name__}: {e}"
            logger.warning(f"[AcousticML] {self.unavailable_reason}")
            return self._result(reason=self.unavailable_reason)

        over = leak_probability >= self.probability_threshold
        # Track quiet-state probability only while below threshold. Letting
        # leak samples into it would drag the baseline up toward the leak and
        # shrink the very delta this exists to show — the same adaptation
        # failure already fixed in the mass balance and acoustic baselines.
        if not over:
            self.baseline_probability = (
                leak_probability if self.baseline_probability is None
                else 0.02 * leak_probability + 0.98 * self.baseline_probability)

        self.consecutive = self.consecutive + 1 if over else 0
        is_alarm = over and self.consecutive >= self.persistence_count

        if is_alarm and self.consecutive == self.persistence_count:
            logger.warning(
                f"[AcousticML] leak probability {leak_probability:.3f} sustained "
                f"{self.consecutive} samples at duty {duty}"
                + ("  [SYNTHETIC MODEL — demonstration only]"
                   if not self.bundle.is_physical else ""))

        return self._result(
            active=True,
            is_alarm=is_alarm,
            # predict_proba IS the channel confidence — no rescaling, so the
            # number the UI shows is the number the model produced.
            confidence=round(leak_probability, 3),
            probability=round(leak_probability, 3),
            consecutive=self.consecutive,
            pump_duty=duty,
            baseline_probability=(round(self.baseline_probability, 3)
                                  if self.baseline_probability is not None else None),
            features={k: round(v, 5) for k, v in features.items()},
            reason=None,
        )

    def _as_model_input(self, vector):
        """Present the vector the way the model was fitted.

        This bundle was trained from a pandas DataFrame, so the estimator carries
        `feature_names_in_`. Handing it a bare list still predicts, but sklearn
        warns that it cannot check the names — and that warning is pointing at a
        real hazard: with names, a column-order mismatch raises; without them, it
        silently scores the wrong feature in the wrong slot and returns a
        confident number. Passing a named frame turns that failure loud.
        """
        names = list(getattr(self.bundle.model, "feature_names_in_", []))
        if names:
            try:
                import pandas as pd
                return pd.DataFrame([vector], columns=names)
            except ImportError:
                pass  # fall through — a list still works, just unchecked
        return [vector]

    def describe(self) -> dict:
        return {
            "method": self.METHOD,
            "enabled": self.enabled,
            "available": self.is_available,
            "unavailable_reason": self.unavailable_reason,
            "probability_threshold": self.probability_threshold,
            "persistence_samples": self.persistence_count,
            "bundle": self.bundle.describe() if self.bundle else None,
        }
