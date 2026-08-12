"""Wire-format adapters for telemetry entering the shared detection pipeline.

The nested Jal Netra MQTT document is the canonical representation.  Older
ESP32 firmware and upstream integrations publish a flat document instead.  Both
are supported at this boundary and nowhere else; downstream code always sees a
``TelemetryDTO``.
"""
from dataclasses import dataclass
from typing import Protocol

from backend.models.telemetry import TelemetryDTO


class TelemetrySchemaError(ValueError):
    """Raised when a payload does not match a supported wire contract."""


class TelemetryAdapter(Protocol):
    name: str

    def matches(self, raw: dict) -> bool: ...

    def normalize(self, raw: dict) -> TelemetryDTO: ...


class NestedTelemetryAdapter:
    name = "nested-v1"

    def matches(self, raw: dict) -> bool:
        return isinstance(raw.get("flow"), dict)

    def normalize(self, raw: dict) -> TelemetryDTO:
        flow = raw.get("flow") or {}
        power = raw.get("power") or {}
        missing = [key for key in ("q_in_lpm", "q_out_lpm") if key not in flow]
        if "current_ma" not in power:
            missing.append("current_ma")
        if "bus_v" not in power and "voltage" not in power:
            missing.append("bus_v")
        if missing:
            raise TelemetrySchemaError(
                f"Missing nested telemetry field(s): {', '.join(missing)}"
            )
        return TelemetryDTO.from_dict(raw)


class FlatEsp32TelemetryAdapter:
    name = "flat-esp32-v1"

    def matches(self, raw: dict) -> bool:
        return any(key in raw for key in ("q_in_lpm", "q_out_lpm"))

    def normalize(self, raw: dict) -> TelemetryDTO:
        power = raw.get("power") if isinstance(raw.get("power"), dict) else {}
        missing = [key for key in ("q_in_lpm", "q_out_lpm") if key not in raw]
        if "current_ma" not in raw and "current_ma" not in power:
            missing.append("current_ma")
        if not any(key in raw for key in ("bus_v", "voltage_v")) and not any(
            key in power for key in ("bus_v", "voltage")
        ):
            missing.append("bus_v")
        if missing:
            raise TelemetrySchemaError(
                f"Missing flat telemetry field(s): {', '.join(missing)}"
            )
        canonical = {
            "ts": raw["ts"],
            "seq": raw.get("seq", 0),
            "device": raw.get("device", raw.get("device_id", "esp32-rig-01")),
            "mode": raw.get("mode", "live"),
            "flow": {
                "q_in_lpm": raw.get("q_in_lpm", 0.0),
                "q_out_lpm": raw.get("q_out_lpm", 0.0),
                "q_branch_lpm": raw.get("q_branch_lpm", 0.0),
                "pulses_in": raw.get("raw_pulses_in", 0),
                "pulses_out": raw.get("raw_pulses_out", 0),
                "pulses_branch": raw.get("raw_pulses_branch", 0),
            },
            "power": {
                "bus_v": power.get(
                    "bus_v", power.get("voltage", raw.get("bus_v", raw.get("voltage_v", 12.0)))
                ),
                "current_ma": power.get("current_ma", raw.get("current_ma", 0.0)),
                "power_mw": power.get("power_mw", raw.get("power_mw", 0.0)),
            },
            "vibration": raw.get("vibration"),
            "temp": raw.get("temp"),
            "actuators": {
                **(raw.get("actuators") if isinstance(raw.get("actuators"), dict) else {}),
                "pump1": (raw.get("actuators") or {}).get("pump1", raw.get("pump_on", False)),
                "pump2": (raw.get("actuators") or {}).get("pump2", False),
                "servo_deg": (raw.get("actuators") or {}).get("servo_deg", raw.get("servo_deg", 0)),
            },
            "health": {
                **(raw.get("health") if isinstance(raw.get("health"), dict) else {}),
                "uptime_s": (raw.get("health") or {}).get("uptime_s", raw.get("uptime_sec", 0)),
                "wifi_rssi": (raw.get("health") or {}).get("wifi_rssi", raw.get("wifi_rssi", -60)),
                "free_heap": (raw.get("health") or {}).get("free_heap", raw.get("heap_free", 180000)),
            },
        }
        return TelemetryDTO.from_dict(canonical)


@dataclass(frozen=True)
class AdaptedTelemetry:
    dto: TelemetryDTO
    wire_schema: str


_ADAPTERS: tuple[TelemetryAdapter, ...] = (
    NestedTelemetryAdapter(),
    FlatEsp32TelemetryAdapter(),
)


def normalize_telemetry(raw: dict) -> AdaptedTelemetry:
    if not isinstance(raw, dict):
        raise TelemetrySchemaError("Payload must be a valid JSON dictionary")
    if "ts" not in raw:
        raise TelemetrySchemaError("Missing required top-level key: 'ts'")

    for adapter in _ADAPTERS:
        if adapter.matches(raw):
            return AdaptedTelemetry(adapter.normalize(raw), adapter.name)

    raise TelemetrySchemaError(
        "No recognizable flow fields - expected nested flow.q_in_lpm/q_out_lpm "
        "or flat q_in_lpm/q_out_lpm"
    )
