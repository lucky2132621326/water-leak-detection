"""Validation for both supported telemetry wire formats.

Wire-format recognition and normalization live in the ingestion adapter.  The
validator is responsible only for enforcing the physical limits shared by Mock
and Live modes.
"""
from backend.ingestion.telemetry_adapter import TelemetrySchemaError, normalize_telemetry
from backend.models.telemetry import TelemetryDTO
from backend.utils.logger import logger

MAX_BUS_VOLTAGE = 24.0


class TelemetryValidator:
    @staticmethod
    def normalize(raw_data: dict) -> tuple[TelemetryDTO | None, str]:
        """Return the canonical DTO, or a human-readable rejection reason."""
        try:
            dto = normalize_telemetry(raw_data).dto

            if dto.flow.q_in_lpm < 0 or dto.flow.q_out_lpm < 0 or dto.flow.q_branch_lpm < 0:
                logger.warning(f"Rejected telemetry seq={dto.seq}: negative flow rate detected")
                return None, "Negative flow rate value detected"

            if dto.power.bus_v < 0.0 or dto.power.bus_v > MAX_BUS_VOLTAGE:
                logger.warning(
                    f"Rejected telemetry seq={dto.seq}: bus voltage out of range "
                    f"({dto.power.bus_v}V)"
                )
                return None, (
                    f"Bus voltage out of valid operational range "
                    f"(0V - {MAX_BUS_VOLTAGE}V)"
                )

            return dto, "VALID"
        except TelemetrySchemaError as exc:
            return None, str(exc)
        except (TypeError, ValueError) as exc:
            logger.error(f"Validation error: {exc}")
            return None, f"Validation exception: {exc}"

    @staticmethod
    def validate(raw_data: dict) -> tuple[bool, str]:
        dto, message = TelemetryValidator.normalize(raw_data)
        return dto is not None, message
