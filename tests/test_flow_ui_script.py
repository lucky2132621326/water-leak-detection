from backend.validators.telemetry_validator import TelemetryValidator
from scripts.flow_ui_test import RATES_LPM, build_packet


def test_rate_program_includes_tiny_values_and_stays_below_three_lpm():
    assert min(RATES_LPM) < 0.05
    assert all(0.0 < rate < 3.0 for rate in RATES_LPM)


def test_packet_is_valid_balanced_telemetry_and_labels_itself_synthetic():
    packet = build_packet(
        rate_lpm=0.01,
        seq=1,
        cycle_litres=0.0002,
        cycle_number=1,
        total_litres=0.0002,
        timestamp=1_786_528_900.0,
    )
    dto, message = TelemetryValidator.normalize(packet)
    assert message == "VALID"
    assert dto is not None
    assert dto.flow.q_in_lpm == 0.01
    assert dto.flow.q_out_lpm == 0.01
    assert packet["test"]["synthetic"] is True
