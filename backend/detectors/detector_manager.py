"""Detector Manager — builds the channel set for the active mode.

The set is NOT fixed. It differs by mode, deliberately:

    LIVE (6)   mass_balance, current_signature, mnf, cusum, acoustic, acoustic_ml
    MOCK (7)   ...the same six, plus pressure_drop

`pressure_drop` exists in mock only. The physical rig has no transducer: a 12V
diaphragm pump develops under 1 bar, while affordable transducers are ranged
0-12 bar, so a real leak's pressure signature would sit beneath the sensor's own
noise floor. The mock channel demonstrates how the system extends to pressure
instrumentation — it is SIMULATED throughout and labelled as such everywhere it
surfaces. Live-mode code never constructs it, so there is no path by which a
simulated pressure can reach a live reading.

Channel independence
--------------------
Only some of these are independent of one another. `mass_balance`, `cusum` and
`mnf` are three statistics of the SAME flow residual, so their agreement is one
measurement counted three times. `current_signature`, `acoustic`, `acoustic_ml`
and (in mock) `pressure_drop` measure different physics with different hardware.
That asymmetry is why fusion weights cross-channel agreement above magnitude on
any single detector, and why the plausibility guard consults only the
flow-independent ones.

`acoustic` and `acoustic_ml` DO share the accelerometer — they are not
independent of each other, though both are independent of the flow meters. They
are weighted accordingly rather than treated as two votes.
"""
import math

from backend.config.config_loader import thresholds_loader
from backend.detectors.acoustic_detector import AcousticDetector
from backend.detectors.acoustic_ml_detector import AcousticMLDetector
from backend.detectors.current_signature_detector import CurrentSignatureDetector
from backend.detectors.cusum_detector import CUSUMDetector
from backend.detectors.mass_balance import MassBalanceDetector
from backend.detectors.mnf_detector import MNFDetector
from backend.detectors.residual import compute_residual
from backend.mode import MODE_MOCK, get_active_mode

#: Channels present in every mode.
CORE_METHODS = ("mass_balance", "current_signature", "cusum", "mnf", "acoustic", "acoustic_ml")
#: Mock-only. See the module docstring for why this cannot exist in live.
MOCK_ONLY_METHODS = ("pressure_drop",)


def methods_for_mode(mode: str = None):
    """The exact channel list for a mode. Used by fusion, the API and the UI so
    all three agree on what is running."""
    resolved = mode or get_active_mode()
    methods = list(CORE_METHODS)
    if resolved == MODE_MOCK:
        methods.extend(MOCK_ONLY_METHODS)
    return methods


class DetectorManager:
    def __init__(self, mode: str = None):
        self.mode = mode or get_active_mode()
        interval_key = "mock_interval_seconds" if self.mode == MODE_MOCK else "live_interval_seconds"
        self.sample_interval_seconds = float(
            thresholds_loader.get(f"telemetry.{interval_key}", 1 if self.mode == MODE_MOCK else 5)
        )
        mass_balance_seconds = float(
            thresholds_loader.get("mass_balance.persistence_seconds", 5)
        )

        self.mass_balance_detector = MassBalanceDetector(
            sigma_threshold=thresholds_loader.get("mass_balance.sigma_threshold", 3.0),
            persistence_count=max(1, math.ceil(mass_balance_seconds / self.sample_interval_seconds)),
            apply_bias=True,
        )
        self.current_detector = CurrentSignatureDetector(
            baseline_ma=thresholds_loader.get("current_signature.baseline_ma", 420.0),
            current_drop_threshold_ma=thresholds_loader.get("current_signature.drop_threshold_ma", 25.0)
        )
        self.cusum_detector = CUSUMDetector(
            slack_k=thresholds_loader.get("cusum.k_allowance", 0.15),
            decision_h=thresholds_loader.get("cusum.h_decision_threshold", 5.0),
            cap_multiple=thresholds_loader.get("cusum.cap_multiple", 2.0),
            reset_after_normal_samples=thresholds_loader.get(
                "cusum.reset_after_normal_samples", 10
            ),
        )
        self.mnf_detector = MNFDetector(
            night_window_start=thresholds_loader.get("mnf.night_window_start", "01:00"),
            night_window_end=thresholds_loader.get("mnf.night_window_end", "05:00"),
            max_allowed_residual_lpm=thresholds_loader.get("mnf.max_allowed_residual_lpm", 0.15)
        )
        self.acoustic_detector = AcousticDetector()
        # Mode-aware: the honesty gate inside refuses a synthetic bundle in live.
        self.acoustic_ml_detector = AcousticMLDetector(mode=self.mode)

        # Constructed ONLY in mock. Imported lazily so a live-mode process never
        # even loads the pressure module — "must not import or reference
        # pressure at all" is enforced by there being no import to reach.
        self.pressure_detector = None
        if self.mode == MODE_MOCK:
            from backend.detectors.simulated_pressure_detector import SimulatedPressureDetector
            self.pressure_detector = SimulatedPressureDetector()

    def methods(self):
        return methods_for_mode(self.mode)

    def process_sample(self, ts, q_in, q_out, q_branch, current_ma, bus_v=12.0,
                       vibration=None, pump_on=True, water_c=None,
                       pump1=True, pump2=False, pressure_bar=None):
        residual = compute_residual(q_in, q_out, q_branch, apply_bias=True)

        mb_res = self.mass_balance_detector.process_sample(q_in, q_out, q_branch)
        mb_res["method"] = "mass_balance"

        curr_res = self.current_detector.analyze(current_ma, q_in, bus_v)
        cusum_res = self.cusum_detector.analyze(residual)
        mnf_res = self.mnf_detector.analyze(ts, residual)
        acoustic_res = self.acoustic_detector.process_sample(
            vibration, pump_on, q_in_lpm=q_in, pump1=pump1, pump2=pump2)
        ml_res = self.acoustic_ml_detector.process_sample(
            vibration, water_c=water_c, q_in_lpm=q_in,
            pump1=pump1, pump2=pump2, pump_on=pump_on)

        results = [mb_res, curr_res, cusum_res, mnf_res, acoustic_res, ml_res]

        if self.pressure_detector is not None:
            results.append(self.pressure_detector.process_sample(
                pressure_bar, residual_lpm=residual, pump_on=pump_on))

        return results

    def describe(self) -> dict:
        return {
            "mode": self.mode,
            "methods": self.methods(),
            "channel_count": len(self.methods()),
            "acoustic_ml": self.acoustic_ml_detector.describe(),
            "pressure_is_simulated": self.pressure_detector is not None,
            "sample_interval_seconds": self.sample_interval_seconds,
        }
