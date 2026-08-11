"""Clock integrity tests.

Two separate ways a wrong clock silently corrupts detection:

1. **The rig's clock.** The ESP32 publishes `millis()/1000` — uptime in seconds
   — as `ts` whenever NTP has not synced yet (`firmware/src/main.cpp`). That is
   a different epoch in the same field, and nothing downstream could tell.

2. **The mock's clock.** Scenarios with no declared `start_time` used to be
   anchored to *now*, so running them between 01:00 and 05:00 local silently
   activated MNF for scenarios never meant to exercise it.

Both matter because MNF is the one detector whose verdict depends on the wall
clock, and because every stored timestamp, alert start time and latency figure
is computed from this field.
"""
import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.ingestion.ingestor import MIN_PLAUSIBLE_TS, repair_timestamp
from backend.mock.generator import MockTelemetryGenerator
from backend.mock.scenarios import BUILTIN_SCENARIOS, get_scenario


class TestTimestampRepair(unittest.TestCase):
    def test_uptime_seconds_are_replaced(self):
        # What the firmware actually publishes pre-NTP: seconds since boot.
        ts, substituted = repair_timestamp({"ts": 1450})
        self.assertTrue(substituted)
        self.assertGreaterEqual(ts, MIN_PLAUSIBLE_TS)

    def test_the_uptime_that_masquerades_as_night_is_replaced(self):
        # ~20 hours of uptime maps into the 01:00-05:00 MNF window once passed
        # to datetime.fromtimestamp — the nastiest case, because MNF then starts
        # evaluating a rig that is not at night.
        ts, substituted = repair_timestamp({"ts": 72000})
        self.assertTrue(substituted)
        self.assertGreaterEqual(ts, MIN_PLAUSIBLE_TS)

    def test_zero_and_missing_are_replaced(self):
        for bad in ({"ts": 0}, {"ts": None}, {}, {"ts": "not-a-number"}):
            with self.subTest(payload=bad):
                _, substituted = repair_timestamp(bad)
                self.assertTrue(substituted)

    def test_runaway_future_clock_is_replaced(self):
        _, substituted = repair_timestamp({"ts": time.time() + 400_000})
        self.assertTrue(substituted)

    def test_a_good_timestamp_is_left_alone(self):
        now = time.time()
        ts, substituted = repair_timestamp({"ts": now})
        self.assertFalse(substituted)
        self.assertEqual(ts, now)

    def test_ordinary_clock_skew_is_tolerated(self):
        # A rig a few minutes off must not have its clock overwritten.
        skewed = time.time() + 300
        _, substituted = repair_timestamp({"ts": skewed})
        self.assertFalse(substituted)


class TestMockClockIsDeterministic(unittest.TestCase):
    def test_scenarios_without_a_start_time_avoid_the_night_window(self):
        # Otherwise detection results depend on what time the suite is run.
        for spec in BUILTIN_SCENARIOS:
            if spec.start_time:
                continue
            with self.subTest(scenario=spec.id):
                gen = MockTelemetryGenerator(spec)
                for offset in (0, spec.duration_sec):
                    hour = time.localtime(gen.base_ts + offset).tm_hour
                    self.assertFalse(
                        1 <= hour < 5,
                        f"{spec.id} runs at {hour:02d}:00 — inside the MNF window")

    def test_night_scenario_really_is_at_night(self):
        # The counterpart: `night_flow` exists solely to reach MNF, and a
        # harness that anchors it outside the window makes the detector
        # unreachable while the scenario still appears to pass.
        gen = MockTelemetryGenerator(get_scenario("night_flow"))
        self.assertEqual(time.localtime(gen.base_ts).tm_hour, 2)

    def test_base_ts_is_never_in_the_future(self):
        for spec in BUILTIN_SCENARIOS:
            with self.subTest(scenario=spec.id):
                self.assertLessEqual(MockTelemetryGenerator(spec).base_ts, time.time())


class TestMNFIsActuallyExercised(unittest.TestCase):
    def test_night_flow_reaches_the_mnf_detector(self):
        """Guards the harness itself.

        `night_flow` passed for a long time with MNF never once evaluated,
        because the scorer pinned base_ts to 0.0 — which resolves to 05:30
        local, just outside the window. The scenario met its recall target on
        the other detectors, so nothing looked wrong.
        """
        from backend.models.telemetry import TelemetryDTO
        from backend.pipeline import DetectionPipeline

        spec = get_scenario("night_flow")
        gen, pipe = MockTelemetryGenerator(spec), DetectionPipeline()
        in_window = 0
        for t in range(spec.duration_sec + 1):
            dto = TelemetryDTO.from_dict(gen.sample_at(float(t)))
            result = pipe.process_sample(
                ts=dto.ts, q_in=dto.flow.q_in_lpm, q_out=dto.flow.q_out_lpm,
                q_branch=dto.flow.q_branch_lpm, current_ma=dto.power.current_ma,
                bus_v=dto.power.bus_v, pump_on=dto.actuators.pump1,
                servo_state_deg=dto.actuators.servo_deg,
                vibration=dto.vibration, water_c=dto.temp.water_c)
            mnf = next(d for d in result["detectors"] if d["method"] == "mnf")
            in_window += bool(mnf["in_night_window"])
        self.assertGreater(in_window, 0, "MNF never evaluated in its own scenario")


if __name__ == "__main__":
    unittest.main()
