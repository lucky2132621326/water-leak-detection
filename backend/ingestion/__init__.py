"""The single telemetry-ingestion boundary used by Mock and Live modes.

Imports are lazy so validation adapters can be used independently without
creating an ingestor/validator import cycle.
"""
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from backend.ingestion.ingestor import TelemetryIngestor, flatten_sample
    from backend.ingestion.telemetry_source import TelemetrySource

__all__ = ["TelemetrySource", "TelemetryIngestor", "flatten_sample"]


def __getattr__(name):
    if name == "TelemetrySource":
        from backend.ingestion.telemetry_source import TelemetrySource
        return TelemetrySource
    if name in ("TelemetryIngestor", "flatten_sample"):
        from backend.ingestion.ingestor import TelemetryIngestor, flatten_sample
        return {"TelemetryIngestor": TelemetryIngestor, "flatten_sample": flatten_sample}[name]
    raise AttributeError(name)
