"""Loading and vetting an acoustic model bundle.

A bundle is a joblib dict:

    {'model', 'features', 'baseline', 'trained_on_runs', 'held_out_runs',
     'n_train', 'note'}

`note` is the honesty marker and the most important field in the file. It is
either:

    'SYNTHETIC — not valid results'          model learned a generator, not a pipe
    'trained on physical ground truth'       model learned from real rig runs

A synthetic-trained classifier is genuinely useful — it proves the whole pipeline
from firmware bands through feature computation to fusion actually works — but
its *output* describes the mock generator's noise model, not pipe acoustics.
Presenting that as a leak probability from real hardware would be fabricating a
measurement. So the note travels with every prediction, all the way to the UI,
and live mode refuses to run a synthetic bundle at all.
"""
import os
import warnings

from backend.utils.logger import logger

#: The exact string that unlocks live mode. Anything else — including a missing
#: note — is treated as synthetic. Defaulting to "trusted" on an unrecognised
#: marker would be precisely the wrong way to fail.
NOTE_PHYSICAL = "trained on physical ground truth"
NOTE_SYNTHETIC = "SYNTHETIC — not valid results"

REQUIRED_KEYS = ("model", "features", "baseline", "note")


class BundleLoadError(Exception):
    """Bundle could not be loaded or is not usable. Never raised past the
    detector — it reports UNAVAILABLE instead."""


class AcousticBundle:
    def __init__(self, path, model, features, baseline, note,
                 trained_on_runs=None, held_out_runs=None, n_train=None,
                 sklearn_warning=None):
        self.path = path
        self.model = model
        self.features = list(features)
        self.baseline = baseline
        self.note = note
        self.trained_on_runs = trained_on_runs or []
        self.held_out_runs = held_out_runs or []
        self.n_train = n_train
        #: Non-None when the bundle was pickled by a different scikit-learn than
        #: the one loading it. Surfaced rather than swallowed: sklearn itself
        #: declines to guarantee predictions across versions.
        self.sklearn_warning = sklearn_warning

    @property
    def is_physical(self) -> bool:
        """True only for a bundle trained on real rig data."""
        return self.note == NOTE_PHYSICAL

    @property
    def duty_levels(self):
        table = self.baseline.get("band_mid_base") or {}
        return sorted(float(k) for k in table.keys())

    def describe(self) -> dict:
        """What the UI shows. `note` is included unconditionally — a caller must
        not be able to render a confidence without also having the caveat."""
        return {
            "path": self.path,
            "note": self.note,
            "is_physical": self.is_physical,
            "features": self.features,
            "n_train": self.n_train,
            "trained_on_runs": self.trained_on_runs,
            "held_out_runs": self.held_out_runs,
            "duty_levels": self.duty_levels,
            "sklearn_warning": self.sklearn_warning,
        }


def load_bundle(path: str) -> AcousticBundle:
    """Load and validate. Raises BundleLoadError on any problem."""
    if not path:
        raise BundleLoadError("no bundle path configured")
    if not os.path.exists(path):
        raise BundleLoadError(f"bundle not found at {path}")

    try:
        import joblib
    except ImportError as e:
        raise BundleLoadError(f"joblib is not installed ({e}) — see requirements.txt")

    # Capture rather than suppress. scikit-learn emits InconsistentVersionWarning
    # when a bundle was pickled by a different version, and its own wording is
    # "might lead to breaking code or invalid results". That is not a detail to
    # hide behind a filter — it rides along on every prediction.
    try:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            raw = joblib.load(path)
        version_notes = [
            str(w.message) for w in caught
            if "version" in str(w.message).lower() and "unpickle" in str(w.message).lower()
        ]
    except Exception as e:
        # Anything at all — a corrupt file, an incompatible pickle protocol, a
        # missing estimator class after an sklearn upgrade. The caller reports
        # UNAVAILABLE; the pipeline must not die because a model file is bad.
        raise BundleLoadError(f"{type(e).__name__}: {e}")

    if not isinstance(raw, dict):
        raise BundleLoadError(
            f"expected a bundle dict, got a bare {type(raw).__name__}. "
            f"Re-export with the {{'model','features','baseline','note',...}} wrapper — "
            f"a bare estimator carries no baseline and no provenance note.")

    missing = [k for k in REQUIRED_KEYS if k not in raw]
    if missing:
        raise BundleLoadError(f"bundle is missing required keys: {', '.join(missing)}")

    if not hasattr(raw["model"], "predict_proba"):
        raise BundleLoadError(
            f"model {type(raw['model']).__name__} has no predict_proba — "
            f"the detector reports calibrated confidence, not a bare class label")

    bundle = AcousticBundle(
        path=path,
        model=raw["model"],
        features=raw["features"],
        baseline=raw["baseline"],
        note=raw["note"],
        trained_on_runs=raw.get("trained_on_runs"),
        held_out_runs=raw.get("held_out_runs"),
        n_train=raw.get("n_train"),
        sklearn_warning=version_notes[0] if version_notes else None,
    )

    n_expected = getattr(bundle.model, "n_features_in_", None)
    if n_expected is not None and n_expected != len(bundle.features):
        raise BundleLoadError(
            f"model expects {n_expected} features but the bundle lists "
            f"{len(bundle.features)}: {bundle.features}")

    if bundle.sklearn_warning:
        logger.warning(
            f"[AcousticML] {os.path.basename(path)} was pickled by a different "
            f"scikit-learn version. Predictions are not guaranteed. "
            f"Detail: {bundle.sklearn_warning}")

    logger.info(
        f"[AcousticML] loaded {os.path.basename(path)} — "
        f"{type(bundle.model).__name__}, {len(bundle.features)} features, "
        f"note={bundle.note!r}")
    return bundle
