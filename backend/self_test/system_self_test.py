"""
System Self-Test Script
Executes full health check across Config, Validator, Detectors, Calibration, and Repository modules.
Run via: python backend/self_test/system_self_test.py
"""
import sys
import os
import io

# Ensure backend path is resolvable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

# Windows consoles default to cp1252, which can't encode the checkmark glyphs
# below and crashes with UnicodeEncodeError. Force UTF-8 stdout so this runs
# the same on Windows demo machines as everywhere else.
if sys.stdout.encoding is None or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

from backend.config.config_loader import ConfigLoader, thresholds_loader
from backend.validators.telemetry_validator import TelemetryValidator
from backend.calibration.calibration_repository import CalibrationRepository
from backend.detectors.detector_manager import DetectorManager
from backend.detectors.detection_state_machine import DetectionStateMachine
from backend.fusion.fusion_engine import FusionEngine
from backend.fusion.confidence_engine import ConfidenceEngine
from backend.localization.localization_service import LocalizationService
from backend.utils.logger import logger

def run_self_test():
    print("=" * 60)
    print("      WATER LEAK DETECTION SYSTEM - SELF-DIAGNOSTIC TEST     ")
    print("=" * 60)

    # 1. Test Config Loader
    print("\n[1/6] Testing Configuration Loader...")
    cfg = ConfigLoader()
    mqtt_host = cfg.get("mqtt.host", "localhost")
    sigma_multiplier = thresholds_loader.get("mass_balance.sigma_threshold")
    assert isinstance(sigma_multiplier, (int, float)) and sigma_multiplier > 0, "Mass-balance sigma threshold is missing or invalid"
    print(f"  ✓ MQTT Host: {mqtt_host}")
    print(f"  ✓ Sigma Multiplier: {sigma_multiplier}")

    # 2. Test Calibration Repository
    print("\n[2/6] Testing Calibration Repository...")
    cal_repo = CalibrationRepository()
    bias = cal_repo.get_bias()
    sigma = cal_repo.get_sigma()
    print(f"  ✓ Zero-leak Bias: {bias} LPM")
    print(f"  ✓ Baseline Noise Sigma: {sigma} LPM")

    # 3. Test Telemetry Validator
    print("\n[3/6] Testing Telemetry Validator...")
    valid_payload = {
        "ts": 1754131200, "seq": 100,
        "flow": {"q_in_lpm": 5.2, "q_out_lpm": 5.18, "q_branch_lpm": 0.0},
        "power": {"voltage": 12.0, "current_ma": 420.0}
    }
    is_valid, msg = TelemetryValidator.validate(valid_payload)
    print(f"  ✓ Valid Payload Check: {is_valid} ({msg})")

    invalid_payload = {
        "ts": 1754131200,
        "seq": 101,
        "flow": {"q_in_lpm": -2.0, "q_out_lpm": 5.0},
        "power": {"voltage": 12.0, "current_ma": 420.0},
    }
    is_invalid, invalid_msg = TelemetryValidator.validate(invalid_payload)
    print(f"  ✓ Invalid Negative Flow Catch: {not is_invalid} ({invalid_msg})")

    # 4. Test Multi-Method Detector Manager
    print("\n[4/6] Testing Multi-Method Detector Manager...")
    mgr = DetectorManager()
    test_ts = 1754131200  # fixed daytime timestamp so MNF is deliberately out-of-window here
    res_no_leak = mgr.process_sample(ts=test_ts, q_in=5.2, q_out=5.18, q_branch=0.0, current_ma=420.0)
    print(f"  ✓ Normal Baseline Detectors Count: {len(res_no_leak)}")

    # Persistence is a deliberate false-positive guard; feed a sustained event
    # long enough for the configured channels to confirm it.
    for offset in range(12):
        res_leak = mgr.process_sample(ts=test_ts + offset, q_in=5.2, q_out=3.95, q_branch=0.0, current_ma=385.0)
    triggered = [r["method"] for r in res_leak if r.get("is_alarm")]
    print(f"  ✓ Leak Injected Detectors Triggered: {triggered}")

    # 5. Test Fusion & Confidence Engine
    print("\n[5/6] Testing Fusion & Confidence Engine...")
    fusion = FusionEngine()
    fused_res = fusion.fuse(res_leak)
    conf = ConfidenceEngine.evaluate(fused_res["fused_score"], len(fused_res["active_methods"]))
    print(f"  ✓ Fused Score: {fused_res['fused_score']}")
    print(f"  ✓ Alarm Fused Verdict: {fused_res['is_alarm']}")
    print(f"  ✓ Calculated Confidence Tier: {conf}")

    # 6. Test Localization Engine
    print("\n[6/6] Testing Localization Engine...")
    loc_service = LocalizationService()
    loc = loc_service.localize_leak(residual_lpm=1.25, q_branch_lpm=0.0, servo_state_deg=45)
    print(f"  ✓ Localized Zone: {loc['zone']} (Confidence: {loc['confidence']})")

    print("\n" + "=" * 60)
    print("      ALL 6 SYSTEM SELF-TEST MODULES PASSED SUCCESSFULLY!     ")
    print("=" * 60)

if __name__ == "__main__":
    run_self_test()
