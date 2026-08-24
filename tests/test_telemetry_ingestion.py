"""Telemetry contract tests — the wire format between firmware, backend and UI.

The canonical schema is nested. The adapter boundary also accepts the upstream
flat ESP32 contract so hardware firmware can migrate independently while every
downstream detector sees the same typed DTO.

Two fields that used to exist are asserted ABSENT, because their hardware does
not exist on this rig:

  * `pressure_bar`    — no transducer, and no estimated substitute either
  * `solenoid_state`  — no solenoid; leaks are opened by hand and ground truth
                        lives in `leak_events` as an operator-logged window

Power, temperature and acoustic fields are nullable because their hardware is
optional. Missing hardware must deactivate its detector, never become fake zero
evidence.
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ingestion.ingestor import TelemetryIngestor, flatten_sample
from backend.models.telemetry import TelemetryDTO
from backend.pipeline import DetectionPipeline
from backend.validators.telemetry_validator import TelemetryValidator


def rig_payload(ts=None, q_in=5.20, q_out=5.18, q_branch=2.10, current_ma=420.0,
                band_mid=0.030, piezo=True, water_c=24.6, seq=None, pump1=True):
    """One sample in the exact shape the firmware publishes."""
    payload = {
        "ts": ts if ts is not None else time.time(),
        "device": "esp32-rig-01",
        "mode": "live",
        "flow": {
            "q_in_lpm": q_in, "q_out_lpm": q_out, "q_branch_lpm": q_branch,
            "pulses_in": 361, "pulses_out": 349, "pulses_branch": 158,
        },
        "power": {"bus_v": 11.94, "current_ma": current_ma, "power_mw": 10056.0},
        "vibration": {
            "rms": 0.042, "band_low": 0.011, "band_mid": band_mid, "band_high": 0.020,
            "piezo_rms": 0.019 if piezo else None,
            "piezo_centroid_hz": 143.2 if piezo else None,
        },
        "temp": {"water_c": water_c},
        "actuators": {"pump1": pump1, "pump2": False, "servo_deg": 0},
        "health": {"uptime_s": 4471, "wifi_rssi": -58, "free_heap": 184320},
    }
    if seq is not None:
        payload["seq"] = seq
    return payload


class TestSchemaShape(unittest.TestCase):
    def test_nested_payload_parses(self):
        dto = TelemetryDTO.from_dict(rig_payload())
        self.assertAlmostEqual(dto.flow.q_in_lpm, 5.20)
        self.assertAlmostEqual(dto.flow.q_out_lpm, 5.18)
        self.assertAlmostEqual(dto.flow.q_branch_lpm, 2.10)
        self.assertAlmostEqual(dto.power.bus_v, 11.94)
        self.assertEqual(dto.device, "esp32-rig-01")

    def test_raw_pulse_counts_survive(self):
        # Non-negotiable (Part G): a later K-factor correction must be
        # applicable to every historical experiment by recomputation, rather
        # than by re-running physical tests.
        dto = TelemetryDTO.from_dict(rig_payload())
        self.assertEqual(dto.flow.pulses_in, 361)
        self.assertEqual(dto.flow.pulses_out, 349)
        self.assertEqual(dto.flow.pulses_branch, 158)

    def test_no_pressure_field_exists(self):
        self.assertFalse(hasattr(TelemetryDTO.from_dict(rig_payload()), "pressure_bar"))

    def test_no_solenoid_field_exists(self):
        actuators = TelemetryDTO.from_dict(rig_payload()).actuators
        self.assertFalse(hasattr(actuators, "solenoid_state"))

    def test_pumps_default_off(self):
        # Relays are ACTIVE-LOW and initialised off at boot (Part H). A rig we
        # have not heard from must not be assumed to be pumping.
        dto = TelemetryDTO.from_dict({"ts": time.time(), "flow": {"q_in_lpm": 0.0}})
        self.assertFalse(dto.actuators.pump1)
        self.assertFalse(dto.actuators.pump2)


class TestOptionalHardware(unittest.TestCase):
    def test_ina219_nulls_are_absence_not_zero(self):
        payload = rig_payload()
        payload["power"] = {"bus_v": None, "current_ma": None, "power_mw": None}
        dto, message = TelemetryValidator.normalize(payload)
        self.assertEqual(message, "VALID")
        self.assertIsNotNone(dto)
        self.assertIsNone(dto.power.bus_v)
        self.assertIsNone(dto.power.current_ma)

    def test_missing_ina219_deactivates_current_detector(self):
        payload = rig_payload()
        payload["power"] = {"bus_v": None, "current_ma": None, "power_mw": None}
        dto = TelemetryDTO.from_dict(payload)
        result = DetectionPipeline(mode="live").process_sample(dto)
        current = next(
            item for item in result["detectors"]
            if item["method"] == "current_signature"
        )
        self.assertFalse(current["active"])
        self.assertFalse(current["is_alarm"])
        self.assertIsNone(current["actual_current_ma"])

    def test_acs712_current_remains_active_without_bus_voltage(self):
        payload = rig_payload()
        payload["power"] = {
            "bus_v": None,
            "current_ma": 386.5,
            "power_mw": None,
            "current_source": "acs712",
        }
        dto, message = TelemetryValidator.normalize(payload)
        self.assertEqual(message, "VALID")
        result = DetectionPipeline(mode="live").process_sample(dto)
        current = next(
            item for item in result["detectors"]
            if item["method"] == "current_signature"
        )
        self.assertTrue(current["active"])
        self.assertFalse(current["voltage_compensated"])
        self.assertEqual(current["actual_current_ma"], 386.5)

    def test_piezo_absent_is_none_not_zero(self):
        # 0.0 is a reading from a silent microphone; None is no microphone.
        # Collapsing the two would make missing hardware look like evidence.
        dto = TelemetryDTO.from_dict(rig_payload(piezo=False))
        self.assertIsNone(dto.vibration.piezo_rms)
        self.assertIsNone(dto.vibration.piezo_centroid_hz)
        self.assertFalse(dto.vibration.has_piezo)

    def test_piezo_present_is_parsed(self):
        dto = TelemetryDTO.from_dict(rig_payload(piezo=True))
        self.assertTrue(dto.vibration.has_piezo)
        self.assertAlmostEqual(dto.vibration.piezo_centroid_hz, 143.2)

    def test_missing_vibration_block_flags_no_accelerometer(self):
        payload = rig_payload()
        del payload["vibration"]
        dto = TelemetryDTO.from_dict(payload)
        self.assertFalse(dto.vibration.has_accelerometer)

    def test_all_null_vibration_flags_no_accelerometer(self):
        payload = rig_payload()
        payload["vibration"] = {k: None for k in payload["vibration"]}
        self.assertFalse(TelemetryDTO.from_dict(payload).vibration.has_accelerometer)

    def test_zero_bands_still_count_as_fitted(self):
        # A genuinely quiet pipe reads zero. That is a measurement, and must not
        # be mistaken for an absent sensor.
        payload = rig_payload()
        payload["vibration"].update(rms=0.0, band_low=0.0, band_mid=0.0, band_high=0.0)
        self.assertTrue(TelemetryDTO.from_dict(payload).vibration.has_accelerometer)

    def test_missing_temperature_probe_is_none(self):
        payload = rig_payload(water_c=None)
        self.assertIsNone(TelemetryDTO.from_dict(payload).temp.water_c)

    def test_unparseable_optional_becomes_none_not_zero(self):
        payload = rig_payload()
        payload["temp"]["water_c"] = "n/a"
        self.assertIsNone(TelemetryDTO.from_dict(payload).temp.water_c)


class TestValidator(unittest.TestCase):
    def test_rig_payload_accepted(self):
        ok, msg = TelemetryValidator.validate(rig_payload())
        self.assertTrue(ok, msg)

    def test_seq_is_not_required(self):
        # The ESP32 does not publish one. Requiring it once rejected 100% of
        # real telemetry; the ingestor assigns a monotonic counter instead.
        ok, _ = TelemetryValidator.validate(rig_payload(seq=None))
        self.assertTrue(ok)

    def test_ts_still_required(self):
        payload = rig_payload()
        del payload["ts"]
        ok, msg = TelemetryValidator.validate(payload)
        self.assertFalse(ok)
        self.assertIn("ts", msg)

    def test_payload_without_flow_fields_is_rejected_not_zeroed(self):
        # The dangerous case: an unexpected shape parses to all-defaults, so a
        # leaking rig is stored as residual 0.0 with no error anywhere.
        ok, msg = TelemetryValidator.validate({"ts": time.time(), "power": {"bus_v": 12.0}})
        self.assertFalse(ok)
        self.assertIn("flow", msg)

    def test_negative_flow_rejected(self):
        ok, _ = TelemetryValidator.validate(rig_payload(q_in=-1.0))
        self.assertFalse(ok)

    def test_out_of_range_bus_voltage_rejected(self):
        payload = rig_payload()
        payload["power"]["bus_v"] = 48.0
        ok, msg = TelemetryValidator.validate(payload)
        self.assertFalse(ok)
        self.assertIn("voltage", msg.lower())

    def test_missing_optional_hardware_is_not_a_rejection(self):
        payload = rig_payload(piezo=False, water_c=None)
        del payload["vibration"]
        ok, msg = TelemetryValidator.validate(payload)
        self.assertTrue(ok, msg)

    def test_non_dict_rejected(self):
        self.assertFalse(TelemetryValidator.validate("not a dict")[0])


class TestFlatten(unittest.TestCase):
    """The dashboard's flat view. Mock and live must flatten identically."""

    def test_fields_are_extracted_from_the_nested_shape(self):
        flat = flatten_sample(rig_payload(ts=1_800_000_000))
        self.assertAlmostEqual(flat["q_in"], 5.20)
        self.assertAlmostEqual(flat["q_out"], 5.18)
        self.assertAlmostEqual(flat["bus_v"], 11.94)
        self.assertAlmostEqual(flat["band_mid"], 0.030)
        self.assertAlmostEqual(flat["water_c"], 24.6)

    def test_residual_ignores_branch_on_this_topology(self):
        # Branch B returns through the outlet meter, so Q_out already contains
        # it. Subtracting q_branch would drive every sample to about -2 L/min.
        flat = flatten_sample(rig_payload(q_in=4.812, q_out=4.655, q_branch=2.104))
        self.assertAlmostEqual(flat["residual"], 0.157, places=3)

    def test_leak_active_is_ground_truth_not_detector_output(self):
        # It reflects an operator-logged clamp window, so the dashboard can
        # honestly show "detector says clear while a clamp is open".
        self.assertFalse(flatten_sample(rig_payload())["leak_active"])
        self.assertTrue(flatten_sample(rig_payload(), leak_active=True)["leak_active"])


class TestIngestion(unittest.TestCase):
    def setUp(self):
        class NoAlerts:
            def ingest(self, *a, **k):
                pass
        self.ingestor = TelemetryIngestor(source_name="test", persist=False,
                                          alert_service=NoAlerts())

    def _run(self, count, base_ts=1_800_000_000, **kwargs):
        last = None
        for i in range(count):
            last = self.ingestor.ingest(rig_payload(ts=base_ts + i, **kwargs))
        return last

    def test_sequence_is_assigned_when_firmware_omits_it(self):
        self.ingestor.ingest(rig_payload(ts=1_800_000_000))
        self.ingestor.ingest(rig_payload(ts=1_800_000_001))
        self.assertEqual(self.ingestor.sample_count, 2)

    def test_flat_esp32_packet_populates_canonical_dashboard_values(self):
        payload = {
            "ts": 1_800_000_000,
            "device_id": "esp32-flat-01",
            "q_in_lpm": 5.2,
            "q_out_lpm": 5.1,
            "q_branch_lpm": 1.4,
            "current_ma": 421.0,
            "bus_v": 11.9,
            "pump_on": True,
        }
        self.assertIsNotNone(self.ingestor.ingest(payload))
        self.assertEqual(self.ingestor.latest_flat["q_in"], 5.2)
        self.assertEqual(self.ingestor.latest_flat["bus_v"], 11.9)
        self.assertEqual(self.ingestor.latest_telemetry["device"], "esp32-flat-01")
        self.assertEqual(self.ingestor.latest_telemetry["power"]["bus_v"], 11.9)

    def test_clean_flow_raises_no_alarm(self):
        response = self._run(60)
        self.assertFalse(response["is_alarm"])

    def test_leak_is_detected_from_rig_shaped_telemetry(self):
        self._run(40)                                     # settle a baseline
        response = self._run(60, base_ts=1_800_000_100,
                             q_out=3.30, current_ma=350.0, band_mid=0.115)
        self.assertTrue(response["is_alarm"])
        self.assertGreater(response["likelihood_score"], 0)

    def test_malformed_payload_is_dropped_not_ingested(self):
        self.assertIsNone(self.ingestor.ingest({"ts": time.time()}))
        self.assertEqual(self.ingestor.rejected_count, 1)
        self.assertEqual(self.ingestor.sample_count, 0)

    def test_response_carries_no_pressure(self):
        response = self._run(5)
        self.assertNotIn("pressure", response)
        self.assertNotIn("pressure_bar", response)
        self.assertNotIn("pressure", response["evidence"].lower())


if __name__ == "__main__":
    unittest.main()
