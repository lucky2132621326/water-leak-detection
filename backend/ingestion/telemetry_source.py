"""Telemetry Source contract.

A source's only job is to produce raw telemetry dicts in the wire format from
docs/MQTT_SPEC.md and hand them to an ingestor. It must not evaluate, score, or
interpret anything — the moment a source starts making detection decisions, the
two modes have diverged.
"""
from abc import ABC, abstractmethod


class TelemetrySource(ABC):
    """Base for anything that feeds the detection pipeline.

    Implementations emit the nested payload documented in MQTT_SPEC.md:

        {"ts", "device", "flow", "power", "vibration", "temp",
         "actuators", "health"}

    Both sources still pass raw payloads through the same validator and DTO.
    """

    #: Stamped onto every stored record and alert so operational KPIs can
    #: exclude synthetic data. Must be "live" or "mock".
    name: str = "unknown"

    @abstractmethod
    def start(self, ingestor) -> None:
        """Begin producing samples into `ingestor.ingest(raw)`."""

    @abstractmethod
    def stop(self) -> None:
        """Stop producing. Must be safe to call when not running."""

    @property
    @abstractmethod
    def is_running(self) -> bool:
        ...

    def describe(self) -> dict:
        """Mode metadata for /api/status and the dashboard's mode indicator."""
        return {"source": self.name, "running": self.is_running}
