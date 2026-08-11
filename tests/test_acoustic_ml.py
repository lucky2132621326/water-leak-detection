"""Tests for the acoustic ML channel.

Two things carry almost all the risk here, and neither is model accuracy:

  1. **The honesty gate.** A classifier trained on generated data must never
     produce numbers about a physical rig. If that gate fails, the system
     reports a fabricated measurement with a confidence attached — the worst
     failure mode this project has.
  2. **Graceful degradation.** An ML channel is the most fragile part of the
     pipeline: a model file can be missing, corrupt, or pickled by another
     library version. None of that may stop leak detection. Five channels
     working beats six channels crashing.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.detectors.acoustic_ml_detector import AcousticMLDetector
from backend.ml.acoustic_features import (
    FeatureUnavailable,
    compute_features,
    resolve_pump_duty,
    to_vector,
)
from backend.ml.bundle import NOTE_PHYSICAL, NOTE_SYNTHETIC, BundleLoadError, load_bundle
from backend.mode import MODE_LIVE, MODE_MOCK
from backend.models.telemetry import VibrationData

BUNDLE = "models/acoustic_clf-2.joblib"

BASELINE = {
    "band_low_base": {0.6: 0.008, 0.8: 0.011, 1.0: 0.014},
    "band_mid_base": {0.6: 0.020, 0.8: 0.027, 1.0: 0.035},
    "band_high_base": {0.6: 0.057, 0.8: 0.078, 1.0: 0.098},
    "rms_base": {0.6: 0.013, 0.8: 0.018, 1.0: 0.023},
}


def vib(band_mid=0.035, piezo=True, accel=True):
    return VibrationData(
        has_accelerometer=accel, rms=0.023, band_low=0.014,
        band_mid=band_mid, band_high=0.098,
        piezo_rms=0.019 if piezo else None,
        piezo_centroid_hz=143.2 if piezo else None,
    )


class TestFeatureComputation(unittest.TestCase):
    def test_ratios_are_against_the_matching_duty(self):
        f = compute_features(0.014, 0.035, 0.098, 0.023, 0.019, 143.2, 24.6,
                             BASELINE, pump_duty=1.0)
        self.assertAlmostEqual(f["ratio_mid"], 1.0, places=2)
        self.assertAlmostEqual(f["ratio_low"], 1.0, places=2)

    def test_duty_keying_actually_changes_the_ratio(self):
        # The whole point of bucketing. Same energies at a lower duty mean the
        # pipe is louder than it should be, and the ratio must say so.
        at_full = compute_features(0.014, 0.035, 0.098, 0.023, 0.019, 143.2, 24.6,
                                   BASELINE, pump_duty=1.0)["ratio_mid"]
        at_low = compute_features(0.014, 0.035, 0.098, 0.023, 0.019, 143.2, 24.6,
                                  BASELINE, pump_duty=0.6)["ratio_mid"]
        self.assertGreater(at_low, at_full * 1.5)

    def test_spectral_tilt_needs_no_baseline(self):
        # Same sensor, same instant, two bands — mounting and duty divide out.
        # This is why it survives a stale or wrongly-bucketed baseline.
        a = compute_features(0.014, 0.035, 0.098, 0.023, 0.019, 143.2, 24.6,
                             BASELINE, pump_duty=1.0)["spectral_tilt"]
        b = compute_features(0.014, 0.035, 0.098, 0.023, 0.019, 143.2, 24.6,
                             BASELINE, pump_duty=0.6)["spectral_tilt"]
        self.assertAlmostEqual(a, b)

    def test_missing_input_raises_rather_than_imputing(self):
        # Filling a gap with a plausible number is how fabricated data reaches
        # a model. Every one of these must refuse.
        for kwargs in ({"piezo_rms": None}, {"water_c": None}, {"piezo_centroid_hz": None}):
            with self.subTest(**kwargs):
                args = dict(band_low=0.014, band_mid=0.035, band_high=0.098, rms=0.023,
                            piezo_rms=0.019, piezo_centroid_hz=143.2, water_c=24.6,
                            baseline=BASELINE, pump_duty=1.0)
                args.update(kwargs)
                with self.assertRaises(FeatureUnavailable):
                    compute_features(**args)

    def test_vector_order_follows_the_bundle_not_a_local_constant(self):
        f = compute_features(0.014, 0.035, 0.098, 0.023, 0.019, 143.2, 24.6,
                             BASELINE, pump_duty=1.0)
        self.assertEqual(to_vector(f, ["water_c", "ratio_mid"]), [24.6, f["ratio_mid"]])

    def test_unknown_feature_name_raises(self):
        # A retrained bundle asking for a feature this build cannot compute must
        # fail loudly. sklearn would happily score any vector of the right length.
        f = compute_features(0.014, 0.035, 0.098, 0.023, 0.019, 143.2, 24.6,
                             BASELINE, pump_duty=1.0)
        with self.assertRaises(FeatureUnavailable):
            to_vector(f, ["ratio_mid", "a_feature_that_does_not_exist"])

    def test_duty_snaps_to_the_nearest_available_bucket(self):
        self.assertEqual(resolve_pump_duty((0.6, 0.8, 1.0), q_in_lpm=5.2, nominal_flow_lpm=5.2), 1.0)
        self.assertEqual(resolve_pump_duty((0.6, 0.8, 1.0), q_in_lpm=3.1, nominal_flow_lpm=5.2), 0.6)


@unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
class TestBundle(unittest.TestCase):
    def test_loads_and_carries_its_note(self):
        b = load_bundle(BUNDLE)
        self.assertIn(b.note, (NOTE_SYNTHETIC, NOTE_PHYSICAL))
        self.assertTrue(hasattr(b.model, "predict_proba"))

    def test_shipped_bundle_is_marked_synthetic(self):
        # If this ever fails, someone re-exported without the honesty marker and
        # the live gate would let it through.
        self.assertFalse(load_bundle(BUNDLE).is_physical)

    def test_describe_always_includes_the_note(self):
        self.assertIn("note", load_bundle(BUNDLE).describe())

    def test_missing_file_raises_a_handled_error(self):
        with self.assertRaises(BundleLoadError):
            load_bundle("models/does-not-exist.joblib")


class TestHonestyGate(unittest.TestCase):
    """The single most important behaviour in this module."""

    @unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
    def test_synthetic_bundle_is_refused_in_live_mode(self):
        d = AcousticMLDetector(mode=MODE_LIVE, bundle_path=BUNDLE, enabled=True)
        self.assertFalse(d.is_available)
        self.assertIn("refused in live mode", d.unavailable_reason)

    @unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
    def test_synthetic_bundle_runs_in_mock_mode(self):
        d = AcousticMLDetector(mode=MODE_MOCK, bundle_path=BUNDLE, enabled=True)
        self.assertTrue(d.is_available)

    @unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
    def test_every_result_carries_the_provenance_note(self):
        # Available or not: a consumer must never be able to obtain a confidence
        # without also having the caveat.
        d = AcousticMLDetector(mode=MODE_MOCK, bundle_path=BUNDLE, enabled=True)
        r = d.process_sample(vib(), water_c=24.6, q_in_lpm=5.2)
        self.assertEqual(r["model_note"], NOTE_SYNTHETIC)
        self.assertTrue(r["is_synthetic_model"])

    def test_disabled_by_default_when_config_key_is_absent(self):
        d = AcousticMLDetector(mode=MODE_MOCK, bundle_path=BUNDLE, enabled=False)
        self.assertFalse(d.is_available)
        self.assertIn("disabled", d.unavailable_reason)


class TestGracefulDegradation(unittest.TestCase):
    """No failure here may take down the pipeline."""

    def _result(self, **kw):
        d = AcousticMLDetector(mode=MODE_MOCK, bundle_path=BUNDLE, enabled=True)
        return d.process_sample(**kw)

    def test_missing_bundle_reports_unavailable_not_crash(self):
        d = AcousticMLDetector(mode=MODE_MOCK, bundle_path="models/nope.joblib", enabled=True)
        r = d.process_sample(vib(), water_c=24.6, q_in_lpm=5.2)
        self.assertFalse(r["active"])
        self.assertFalse(r["is_alarm"])
        self.assertIsNotNone(r["reason"])

    @unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
    def test_no_accelerometer_reports_unavailable(self):
        r = self._result(vibration=vib(accel=False), water_c=24.6, q_in_lpm=5.2)
        self.assertFalse(r["active"])

    @unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
    def test_absent_piezo_reports_unavailable_not_zero(self):
        # The model needs all eight features. Substituting 0.0 for an absent
        # microphone would be inventing a reading.
        r = self._result(vibration=vib(piezo=False), water_c=24.6, q_in_lpm=5.2)
        self.assertFalse(r["active"])

    @unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
    def test_absent_water_temperature_reports_unavailable(self):
        r = self._result(vibration=vib(), water_c=None, q_in_lpm=5.2)
        self.assertFalse(r["active"])

    @unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
    def test_pump_off_stands_down(self):
        r = self._result(vibration=vib(), water_c=24.6, q_in_lpm=5.2, pump_on=False)
        self.assertFalse(r["active"])

    @unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
    def test_none_vibration_reports_unavailable(self):
        r = self._result(vibration=None, water_c=24.6, q_in_lpm=5.2)
        self.assertFalse(r["active"])


@unittest.skipUnless(os.path.exists(BUNDLE), f"{BUNDLE} not present")
class TestPersistence(unittest.TestCase):
    def test_a_single_positive_frame_does_not_alarm(self):
        # A cavitation burst is one loud frame with no leak behind it. The
        # persistence requirement is what separates it from a real leak.
        d = AcousticMLDetector(mode=MODE_MOCK, bundle_path=BUNDLE, enabled=True,
                               probability_threshold=0.0, persistence_count=5)
        r = d.process_sample(vib(band_mid=0.3), water_c=24.6, q_in_lpm=5.2)
        self.assertTrue(r["active"])
        self.assertFalse(r["is_alarm"])

    def test_sustained_positives_do_alarm(self):
        d = AcousticMLDetector(mode=MODE_MOCK, bundle_path=BUNDLE, enabled=True,
                               probability_threshold=0.0, persistence_count=3)
        for _ in range(3):
            r = d.process_sample(vib(band_mid=0.3), water_c=24.6, q_in_lpm=5.2)
        self.assertTrue(r["is_alarm"])

    def test_a_clean_frame_resets_the_counter(self):
        d = AcousticMLDetector(mode=MODE_MOCK, bundle_path=BUNDLE, enabled=True,
                               probability_threshold=1.1, persistence_count=2)
        d.process_sample(vib(band_mid=0.3), water_c=24.6, q_in_lpm=5.2)
        r = d.process_sample(vib(band_mid=0.3), water_c=24.6, q_in_lpm=5.2)
        self.assertEqual(r["consecutive"], 0)


if __name__ == "__main__":
    unittest.main()
