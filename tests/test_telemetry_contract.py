from backend.models.telemetry import TelemetryDTO
from backend.validators.telemetry_validator import TelemetryValidator


def _firmware_payload():
    return {
        "ts": 1_722_686_947,
        "seq": 1842,
        "device_id": "esp32_rig_01",
        "q_in_lpm": 5.20,
        "q_out_lpm": 3.92,
        "q_branch_lpm": 0.03,
        "current_ma": 390.5,
        "voltage_v": 12.1,
        "raw_pulses_in": 2368,
        "raw_pulses_out": 2345,
        "raw_pulses_branch": 12,
        "pump_on": True,
        "solenoid_state": True,
        "servo_deg": 45,
    }


def test_flat_esp32_payload_maps_to_canonical_dto():
    raw = _firmware_payload()
    dto, message = TelemetryValidator.normalize(raw)

    assert message == "VALID"
    assert dto is not None
    assert dto.device_id == "esp32_rig_01"
    assert dto.seq == 1842
    assert dto.flow.q_in_lpm == 5.20
    assert dto.flow.q_out_lpm == 3.92
    assert dto.flow.pulses_branch == 12
    assert dto.power.current_ma == 390.5
    assert dto.actuators.pump1 is True
    assert dto.actuators.servo_deg == 45


def test_legacy_firmware_packet_without_seq_is_accepted():
    raw = _firmware_payload()
    raw.pop("seq")

    valid, message = TelemetryValidator.validate(raw)

    assert (valid, message) == (True, "VALID")
    dto, _ = TelemetryValidator.normalize(raw)
    assert dto.seq == 0


def test_incomplete_flat_packet_is_rejected():
    raw = _firmware_payload()
    raw.pop("current_ma")

    valid, message = TelemetryValidator.validate(raw)

    assert valid is False
    assert "current_ma" in message


def test_nested_replay_payload_remains_supported():
    raw = {
        "ts": 1_722_686_947,
        "seq": 9,
        "device_id": "replay_RUN_001",
        "flow": {"q_in_lpm": 5.1, "q_out_lpm": 5.0, "q_branch_lpm": 0.0},
        "power": {"voltage": 12.0, "current_ma": 421.0},
        "actuators": {"pump1": True, "pump2": False, "servo_deg": 0},
    }

    valid, message = TelemetryValidator.validate(raw)
    dto = TelemetryDTO.from_dict(raw)

    assert (valid, message) == (True, "VALID")
    assert dto.flow.q_in_lpm == 5.1
    assert dto.power.voltage == 12.0


def test_hardware_owner_nested_wire_schema_is_supported():
    raw = {
        "ts": 1_754_131_200.123,
        "seq": 4471,
        "device": "esp32-rig-01",
        "flow": {
            "q_in_lpm": 4.812,
            "q_out_lpm": 4.655,
            "q_branch_lpm": 2.104,
            "pulses_in": 361,
            "pulses_out": 349,
            "pulses_branch": 158,
        },
        "power": {"bus_v": 11.94, "current_ma": 842.3, "power_mw": 10056.0},
        "actuators": {"pump1": True, "pump2": False, "servo_deg": 0},
        "health": {"uptime_s": 4471, "wifi_rssi": -58, "free_heap": 184320},
    }

    valid, message = TelemetryValidator.validate(raw)
    dto = TelemetryDTO.from_dict(raw)

    assert (valid, message) == (True, "VALID")
    assert dto.device_id == "esp32-rig-01"
    assert dto.power.voltage == 11.94
    assert dto.flow.pulses_branch == 158
    assert dto.health.uptime_s == 4471


def test_flat_bus_v_and_hardware_metadata_are_normalized():
    raw = _firmware_payload()
    raw.pop("voltage_v")
    raw["bus_v"] = 11.87

    dto, message = TelemetryValidator.normalize(raw)

    assert message == "VALID"
    assert dto is not None
    assert dto.power.bus_v == 11.87
    assert dto.device_id == "esp32_rig_01"
    assert dto.to_dict()["power"]["bus_v"] == 11.87
