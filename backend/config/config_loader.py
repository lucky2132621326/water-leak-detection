"""
Configuration Loader
Loads runtime system parameters from backend/config/settings.yaml into a unified config dictionary.
"""
import os
import yaml
from backend.utils.logger import logger

class ConfigLoader:
    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ConfigLoader, cls).__new__(cls)
            cls._instance.load_config()
        return cls._instance

    def load_config(self, filepath: str = "backend/config/settings.yaml"):
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r') as f:
                    self._config = yaml.safe_load(f)
                    logger.info(f"Loaded dynamic configuration from {filepath}")
            except Exception as e:
                logger.error(f"Error loading {filepath}: {e}, using default fallback")
                self._config = self.get_defaults()
        else:
            logger.warning(f"Config file {filepath} not found, using default fallback settings")
            self._config = self.get_defaults()

    def get_defaults(self):
        return {
            "mqtt": {"host": "localhost", "port": 1883, "topic": "rig/telemetry", "status_topic": "rig/status", "cmd_topic": "rig/cmd"},
            "database": {"uri": "mongodb://localhost:27017", "name": "water_leak_detection"},
            "hydraulics": {"topology": "recombined_branch", "zero_leak_bias_lpm": 0.02},
            "detector": {
                "sigma_multiplier": 3.0,
                "persistence_seconds": 10,
                "bias_lpm": 0.10,
                "current_drop_threshold_ma": 20.0,
                "cusum_slack_k": 0.15,
                "cusum_decision_h": 3.0
            }
        }

    def get(self, key_path: str, default=None):
        env_overrides = {
            "mqtt.host": "MQTT_HOST",
            "mqtt.port": "MQTT_PORT",
            "database.uri": "MONGO_URI",
            "database.name": "MONGO_DB_NAME",
        }
        env_name = env_overrides.get(key_path)
        if env_name and os.getenv(env_name) is not None:
            value = os.getenv(env_name)
            return int(value) if key_path == "mqtt.port" else value

        keys = key_path.split(".")
        val = self._config
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

config_loader = ConfigLoader()


class ThresholdsLoader:
    """Loads backend/config/thresholds.yaml (per-detector tuning knobs) —
    kept separate from settings.yaml (infra config) since calibration engineers
    and infra changes shouldn't touch the same file."""
    _instance = None
    _thresholds = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ThresholdsLoader, cls).__new__(cls)
            cls._instance.load()
        return cls._instance

    def load(self, filepath: str = "backend/config/thresholds.yaml"):
        try:
            with open(filepath, 'r') as f:
                self._thresholds = yaml.safe_load(f)
                logger.info(f"Loaded detector thresholds from {filepath}")
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}, using built-in defaults")
            self._thresholds = {
                "mass_balance": {"sigma_threshold": 3.0, "persistence_seconds": 5, "zero_flow_tolerance": 0.05},
                "current_signature": {"drop_threshold_ma": 25.0, "baseline_ma": 420.0},
                "mnf": {"night_window_start": "01:00", "night_window_end": "05:00", "max_allowed_residual_lpm": 0.15},
                "cusum": {"k_allowance": 0.15, "h_decision_threshold": 5.0},
                "fusion": {"high_alarm_confidence": 0.75, "medium_alarm_confidence": 0.50}
            }

    def get(self, key_path: str, default=None):
        keys = key_path.split(".")
        val = self._thresholds
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

thresholds_loader = ThresholdsLoader()


class ImpactLoader:
    """Loads backend/config/impact.yaml (water tariff, severity bands, relatable
    equivalents). Separate from thresholds.yaml because these are operator/utility
    business inputs, not detector tuning knobs."""
    _instance = None
    _impact = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(ImpactLoader, cls).__new__(cls)
            cls._instance.load()
        return cls._instance

    def load(self, filepath: str = "backend/config/impact.yaml"):
        try:
            with open(filepath, 'r') as f:
                self._impact = yaml.safe_load(f)
                logger.info(f"Loaded impact configuration from {filepath}")
        except Exception as e:
            logger.error(f"Error loading {filepath}: {e}, using built-in defaults")
            self._impact = self.get_defaults()

    @staticmethod
    def get_defaults():
        return {
            "tariff": {"currency_symbol": "₹", "rate_per_kilolitre": 20.0},
            "severity_bands": [
                {"max_lpm": 0.2, "label": "MINOR"},
                {"max_lpm": 0.5, "label": "MODERATE"},
                {"max_lpm": 1.0, "label": "MAJOR"},
            ],
            "critical_label": "CRITICAL",
            "equivalents": {"tank_litres": 200, "person_daily_litres": 135, "bucket_litres": 20},
            "recommendation": {"immediate_lpm": 1.0, "urgent_lpm": 0.5, "scheduled_lpm": 0.2},
            "progression": {"delay_options_days": [1, 7, 30, 90, 365], "default_delay_days": 30},
        }

    def get(self, key_path: str, default=None):
        keys = key_path.split(".")
        val = self._impact
        for k in keys:
            if isinstance(val, dict) and k in val:
                val = val[k]
            else:
                return default
        return val

impact_loader = ImpactLoader()
