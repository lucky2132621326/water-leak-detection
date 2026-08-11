"""Telemetry Validator

Rejects payloads that cannot be trusted, before they reach a detector or the
database. The bar is deliberately narrow: reject what would be *silently wrong*,
repair what is merely inconvenient, and let everything else through.

Two rejections earn their place because both previously failed silently:

  * **No recognizable flow block.** An unexpected shape parses to all-defaults,
    so a leaking rig gets stored as residual 0.0 with no error anywhere. A
    rejection is loud; a zero is not.
  * **Negative flow or out-of-range bus voltage.** Physically impossible, so the
    reading is corrupt regardless of what it would imply.

Deliberately NOT rejected:

  * **`seq`** — the ESP32 does not publish one. Requiring it once rejected 100%
    of real telemetry. The ingestor assigns a monotonic counter instead.
  * **An implausible `ts`** — repaired, not rejected. The firmware publishes
    uptime instead of an epoch until NTP syncs; the flow data in that packet is
    perfectly good. See `backend/ingestion/ingestor.py::repair_timestamp`.
  * **Missing `vibration` or `temp`** — both are optional hardware. Detection
    degrades to the channels that are present.
"""
from backend.models.telemetry import TelemetryDTO
from backend.utils.logger import logger

#: The rig runs on a 12V supply; the INA219 measures the bus directly. Anything
#: outside this band is a wiring or sensor fault, not a real operating point.
MAX_BUS_VOLTAGE = 24.0


class TelemetryValidator:
    @staticmethod
    def _has_flow_fields(raw_data: dict) -> bool:
        flow = raw_data.get("flow")
        return (
            isinstance(flow, dict)
            and any(k in flow for k in ("q_in_lpm", "q_out_lpm", "q_branch_lpm"))
        ) or any(k in raw_data for k in ("q_in_lpm", "q_out_lpm", "q_branch_lpm"))

    @staticmethod
    def validate(raw_data: dict) -> tuple[bool, str]:
        if not isinstance(raw_data, dict):
            return False, "Payload must be a valid JSON dictionary"

        if "ts" not in raw_data:
            return False, "Missing required top-level key: 'ts'"

        is_flat = any(k in raw_data for k in ("q_in_lpm", "q_out_lpm"))
        if is_flat:
            missing = [
                key for key in ("q_in_lpm", "q_out_lpm", "current_ma", "voltage_v")
                if key not in raw_data
            ]
            if missing:
                return False, f"Missing required telemetry field(s): {', '.join(missing)}"
        elif not TelemetryValidator._has_flow_fields(raw_data):
            return False, (
                "No recognizable flow fields — expected a nested 'flow' object "
                "with q_in_lpm/q_out_lpm per docs/MQTT_SPEC.md"
            )

        else:
            flow = raw_data.get("flow") or {}
            power = raw_data.get("power") or {}
            missing = [key for key in ("q_in_lpm", "q_out_lpm") if key not in flow]
            missing += [key for key in ("current_ma",) if key not in power]
            if "bus_v" not in power and "voltage" not in power:
                missing.append("bus_v")
            if missing:
                return False, f"Missing nested telemetry field(s): {', '.join(missing)}"

        try:
            dto = TelemetryDTO.from_dict(raw_data)

            if dto.flow.q_in_lpm < 0 or dto.flow.q_out_lpm < 0 or dto.flow.q_branch_lpm < 0:
                logger.warning(f"Rejected telemetry seq={dto.seq}: negative flow rate detected")
                return False, "Negative flow rate value detected"

            if dto.power.bus_v < 0.0 or dto.power.bus_v > MAX_BUS_VOLTAGE:
                logger.warning(f"Rejected telemetry seq={dto.seq}: bus voltage out of range ({dto.power.bus_v}V)")
                return False, f"Bus voltage out of valid operational range (0V - {MAX_BUS_VOLTAGE}V)"

            return True, "VALID"
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False, f"Validation exception: {str(e)}"
