"""
Telemetry Validator Module
Rejects corrupted packets, negative flow values, and invalid timestamp payloads before database storage.
"""
import math

from backend.models.telemetry import TelemetryDTO
from backend.utils.logger import logger

class TelemetryValidator:
    @staticmethod
    def validate(raw_data: dict) -> tuple[bool, str]:
        if not isinstance(raw_data, dict):
            return False, "Payload must be a valid JSON dictionary"

        if "ts" not in raw_data:
            return False, "Missing required top-level key: 'ts'"

        is_flat_wire_payload = "q_in_lpm" in raw_data or "q_out_lpm" in raw_data
        if is_flat_wire_payload:
            missing = [key for key in ("q_in_lpm", "q_out_lpm", "current_ma", "voltage_v") if key not in raw_data]
            if missing:
                return False, f"Missing required telemetry field(s): {', '.join(missing)}"
        elif not isinstance(raw_data.get("flow"), dict) or not isinstance(raw_data.get("power"), dict):
            return False, "Telemetry must contain flat sensor fields or nested 'flow' and 'power' objects"
        else:
            flow = raw_data["flow"]
            power = raw_data["power"]
            missing_flow = [key for key in ("q_in_lpm", "q_out_lpm") if key not in flow]
            missing_power = [key for key in ("current_ma",) if key not in power]
            if "voltage" not in power and "bus_v" not in power:
                missing_power.append("bus_v")
            if missing_flow or missing_power:
                return False, f"Missing nested telemetry field(s): {', '.join(missing_flow + missing_power)}"

        try:
            dto = TelemetryDTO.from_dict(raw_data)

            if not math.isfinite(float(dto.ts)) or float(dto.ts) <= 0:
                return False, "Timestamp must be a positive finite number"
            if dto.seq < 0:
                return False, "Sequence number must be non-negative"
            
            # Check for illegal negative flow rates
            if dto.flow.q_in_lpm < 0 or dto.flow.q_out_lpm < 0 or dto.flow.q_branch_lpm < 0:
                logger.warning(f"Rejected telemetry seq={dto.seq}: negative flow rate detected")
                return False, "Negative flow rate value detected"

            # Check for unreasonable voltage
            if dto.power.voltage < 0.0 or dto.power.voltage > 24.0:
                logger.warning(f"Rejected telemetry seq={dto.seq}: voltage out of range ({dto.power.voltage}V)")
                return False, "Voltage out of valid operational range (0V - 24V)"

            if max(dto.flow.q_in_lpm, dto.flow.q_out_lpm, dto.flow.q_branch_lpm) > 200.0:
                return False, "Flow value exceeds supported sensor range (200 L/min)"

            return True, "VALID"
        except Exception as e:
            logger.error(f"Validation error: {e}")
            return False, f"Validation exception: {str(e)}"
