"""Telemetry Ingestion

The single door every telemetry sample enters through, regardless of origin.

The system has exactly two operating modes, and they differ ONLY in where
samples come from:

    MockTelemetrySource  ─┐
                          ├─→ TelemetryIngestor ─→ validate → DTO → pipeline
    MqttTelemetrySource  ─┘                        → fusion → confidence
                                                   → localization → alerts
                                                   → impact → dashboard

Both sources emit the identical flat wire format defined in docs/MQTT_SPEC.md,
so mock data is not "fed in differently" — it arrives at the same validator, is
parsed by the same DTO, and is evaluated by the same detectors. Divergence
between modes is prevented structurally rather than by convention.
"""
from backend.ingestion.telemetry_source import TelemetrySource
from backend.ingestion.ingestor import TelemetryIngestor, flatten_sample

__all__ = ["TelemetrySource", "TelemetryIngestor", "flatten_sample"]
