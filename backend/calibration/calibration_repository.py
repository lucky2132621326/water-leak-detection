"""
Calibration Repository
Stores and loads dynamic calibration matrices (K-factors, baseline bias, sigma noise bounds).
"""
import json
import os
from backend.utils.logger import logger

class CalibrationRepository:
    def __init__(self, filepath="backend/calibration/calibration_data.json"):
        self.filepath = filepath
        self.data = self.load_calibration()

    def load_calibration(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logger.error(f"Failed to load calibration data from {self.filepath}: {e}")
        
        # Default zero-leak baseline calibration values
        return {
            "flow1_k": 445.2,
            "flow2_k": 451.8,
            "flow3_k": 447.1,
            "bias_lpm": 0.02,
            "sigma_lpm": 0.03,
            "ina219_no_load_ma": 420.0,
            "ina219_load_slope": 2.5,
            "vib_baseline_band_mid": 0.015,
            "vib_baseline_status": "PROVISIONAL — no real MPU6050 characterised yet",
            "temp_k_coeff": 0.0,
            "temp_reference_c": 24.0,
            "clamp_calibration": {
                "TEE_A": {"0.25": 0.18, "0.50": 0.34, "0.75": 0.51, "1.00": 0.72},
                "TEE_B": {"0.25": 0.17, "0.50": 0.33, "0.75": 0.50, "1.00": 0.70},
                "TEE_C": {"0.25": 0.19, "0.50": 0.35, "0.75": 0.53, "1.00": 0.74}
            },
            "clamp_calibration_status": "PROVISIONAL — replace with volumetric test results",
            "calibrated_at": 1754131200
        }

    def save_calibration(self, calibration_dict: dict):
        self.data.update(calibration_dict)
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        with open(self.filepath, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2)
        logger.info(f"Updated calibration repository at {self.filepath}")

    def get_bias(self) -> float:
        return self.data.get("bias_lpm", 0.02)

    def get_sigma(self) -> float:
        return self.data.get("sigma_lpm", 0.03)

    def get_vib_baseline_band_mid(self) -> float:
        return self.data.get("vib_baseline_band_mid", 0.015)

    def get_temp_k_coeff(self) -> float:
        return self.data.get("temp_k_coeff", 0.0)

    def get_temp_reference_c(self) -> float:
        return self.data.get("temp_reference_c", 24.0)
