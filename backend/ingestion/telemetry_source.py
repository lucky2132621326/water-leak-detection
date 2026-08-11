"""Telemetry Source contract.

A source's only job is to produce raw telemetry dicts in the wire format from
docs/MQTT_SPEC.md and hand them to an ingestor. It must not evaluate, score, or
interpret anything — the moment a source starts making detection decisions, the
two modes have diverged.
"""
from abc import ABC, abstractmethod


class TelemetrySource(ABC):
    """Base for anything that feeds the detection pipeline.

    Implementations must emit the FLAT payload shape the ESP32 publishes:

        {"ts", "device_id", "q_in_lpm", "q_out_lpm", "q_branch_lpm",
         "current_ma", "voltage_v", "solenoid_state",
         "pulses_in", "pulses_out", "pulses_branch"}

    Emitting anything else would route mock data around the validator and the
    DTO, which is exactly the class of drift this abstraction exists to stop.
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
