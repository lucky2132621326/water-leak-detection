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
        
        # Defaults mirror firmware/src/config.h. They must match what is
        # actually flashed — K-factors live in the firmware and are applied
        # on-device, so a mismatch here would misreport the rig's real
        # conversion constants.
        return {
            "flow1_k": 456.0,
            "flow2_k": 448.0,
            "flow3_k": 452.0,
            "bias_lpm": 0.02,
            "sigma_lpm": 0.03,
            "ina219_no_load_ma": 420.0,
            "ina219_load_slope": 2.5,
            "calibrated_at": None,
            "source": "firmware defaults (not yet field-calibrated)"
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
