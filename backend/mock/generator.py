"""Mock telemetry generator.

Turns a ScenarioSpec into the exact nested payload the ESP32 publishes on
`rig/telemetry` (docs/MQTT_SPEC.md, spec Part G). Emitting the real wire format
— rather than a convenient internal structure — is what forces mock data through
the same validator, DTO, detectors and persistence as live data.

Why physical fidelity is not optional
-------------------------------------
Mock data exists to prove the detection logic correct. If it is not physically
faithful it proves nothing: a detector tuned against unrealistic data is tuned
against a fiction. So every effect the detectors actually key on is modelled here
with the right shape, units and magnitude.

Physical model
--------------
On this rig Branch B returns through the outlet meter, so Q_out already contains
Q_branch and the residual is:

    R = Q_in - Q_out - bias

Q_out is therefore built as `q_in - total_leak - bias`, and `q_branch` is
generated as an independent in-loop measurement that does NOT enter the residual.
Getting this wrong is exactly the topology error the backend used to make.

Modelled effects, each because a detector depends on it:

  * **Independent per-meter noise** — the residual inherits both, which is why a
    small nonzero residual exists with no leak.
  * **K-factor bias** — a permanent offset between two physically different
    meters, the thing `calibration.bias_lpm` cancels.
  * **~2 s leak onset ramp** — a clamp opened by hand is not a step.
  * **Pump current shift** — a leak lowers hydraulic resistance, so P1 draws less.
  * **Vibration band_mid rise** — the leak jet excites the pipe wall at 50-150 Hz.
  * **Thermal drift** — the pump warms the reservoir, K-factor drifts with
    viscosity, and the residual baseline walks. Uncorrected this mimics a slow leak.
  * **Variable demand** — P2 cycling, the realistic hard case.
  * **Raw pulse counts** — derived from the configured K-factors and the emitted
    rates, so they stay mutually consistent and a K-factor recalibration can be
    replayed over stored data.
"""
import math
import random
import time
from typing import Iterator, Optional

from backend.config.config_loader import thresholds_loader
from backend.mock.scenarios import MAIN, ScenarioSpec


class MockTelemetryGenerator:
    #: Clock a scenario runs at when it does not name one. MNF evaluates only
    #: between 01:00 and 05:00, so this must sit firmly outside that window.
    DEFAULT_START_TIME = "12:00"

    def __init__(self, scenario: ScenarioSpec, base_ts: Optional[float] = None):
        self.scenario = scenario
        self.rng = random.Random(scenario.seed)
        self.base_ts = base_ts if base_ts is not None else self._resolve_base_ts(scenario)
        self._pulses_in = 0
        self._pulses_out = 0
        self._pulses_branch = 0
        self._stuck_value = None
        self._seq = 0
        #: Per-run mounting gain, drawn once. A hand-fitted accelerometer couples
        #: to the pipe differently every time it is refitted, so absolute band
        #: energies are not comparable across runs — only ratios are. Varying it
        #: per run means anything that accidentally depends on absolute level
        #: fails here rather than on the bench.
        self._mount_gain = 1.0 + self.rng.gauss(0.0, scenario.vib_mount_gain_spread / 2.0)
        self._mount_gain = max(0.35, self._mount_gain)

        # K-factors come from the same config the backend converts with, so mock
        # pulse counts and mock rates cannot disagree.
        self.k1 = float(thresholds_loader.get("calibration.k1_pulses_per_litre", 450.0))
        self.k2 = float(thresholds_loader.get("calibration.k2_pulses_per_litre", 450.0))
        self.k3 = float(thresholds_loader.get("calibration.k3_pulses_per_litre", 450.0))

    @staticmethod
    def _resolve_base_ts(scenario: ScenarioSpec) -> float:
        """Anchor the run to a wall-clock time.

        Scenarios that name no time are anchored to midday rather than to *now*.
        Using `now` made every scenario's behaviour depend on when it happened to
        run: start the suite between 01:00 and 05:00 local and MNF silently
        activates for scenarios never meant to exercise it. Detection results
        must not change because of the hour on the wall.
        """
        start_time = scenario.start_time or MockTelemetryGenerator.DEFAULT_START_TIME
        hh, mm = (int(p) for p in start_time.split(":"))
        now = time.localtime()
        anchored = time.struct_time((
            now.tm_year, now.tm_mon, now.tm_mday, hh, mm, 0,
            now.tm_wday, now.tm_yday, -1,
        ))
        base = time.mktime(anchored)
        return base - 86400 if base > time.time() else base

    # --- environment ------------------------------------------------------
    def _active_faults(self, t: float):
        return [f for f in self.scenario.faults if f.is_active_at(t)]

    def _noise(self, t: float) -> float:
        sigma = self.scenario.noise_sigma_lpm
        for f in self._active_faults(t):
            if f.kind == "noise_burst":
                sigma *= f.magnitude
        return self.rng.gauss(0.0, sigma)

    def _water_temp(self, t: float) -> float:
        """Reservoir warms as the pump does work on the water."""
        return self.scenario.water_c_start + self.scenario.water_c_rise_per_hour * (t / 3600.0)

    def _k_drift(self, t: float) -> float:
        """Fractional K-factor error from thermal drift.

        Viscosity falls as the water warms, so the meters read slightly
        differently than they did when calibrated. Applied to the OUTLET meter
        only, so it shows up as residual drift — the realistic failure, and the
        one the DS18B20 correction exists to cancel.
        """
        coeff = float(thresholds_loader.get("calibration.temp_k_coeff_per_c", 0.0))
        reference = float(thresholds_loader.get("calibration.temp_reference_c", 25.0))
        # A small intrinsic drift is always present in the mock even when the
        # backend's correction coefficient is left at its 0.0 default — the
        # physics happens whether or not anyone has characterised it yet.
        intrinsic = 0.0015
        return (self._water_temp(t) - reference) * (coeff or intrinsic)

    def _demand_offset(self, t: float) -> float:
        """P2 cycling. Legitimate demand variation, not a leak."""
        if self.scenario.demand_mode != "variable":
            return 0.0
        phase = 2 * math.pi * t / max(1e-6, self.scenario.demand_period_sec)
        return self.scenario.demand_swing_lpm * math.sin(phase)

    def _pump2_on(self, t: float) -> bool:
        return self.scenario.demand_mode == "variable" and self._demand_offset(t) > 0

    # --- sample synthesis -------------------------------------------------
    def sample_at(self, t: float, leak_override: dict = None, ts_override: float = None) -> dict:
        """Synthesize one sample in the Part G wire format.

        `leak_override` (from MockLeakControl) takes complete precedence over the
        scenario's scripted leaks — it replaces them rather than adding to them,
        so closing a manually-opened valve cannot silently re-expose a scripted
        leak underneath.
        """
        s = self.scenario
        kinds = {f.kind for f in self._active_faults(t)}

        if leak_override and leak_override.get("overriding"):
            total_leak = float(leak_override.get("effective_rate_lpm", 0.0))
            leak_location = leak_override.get("location", MAIN)
        else:
            total_leak = sum(l.rate_at(t) for l in s.leaks)
            active = [l for l in s.leaks if l.is_active_at(t) and l.rate_at(t) > 0]
            leak_location = max(active, key=lambda l: l.rate_at(t)).location if active else MAIN

        demand = self._demand_offset(t)

        # --- flow -----------------------------------------------------------
        q_in = s.baseline_flow_lpm + demand + self._noise(t)
        # Branch B is IN-LOOP: it returns through the outlet meter, so it is a
        # separate measurement that must NOT be subtracted from the residual.
        q_branch = max(0.0, s.branch_flow_lpm + demand * 0.3 + self._noise(t) * 0.4)
        # Everything that entered leaves, minus what escaped, minus the permanent
        # meter mismatch, minus thermal K-factor drift on this meter.
        q_out = (q_in - total_leak) * (1.0 - self._k_drift(t)) - s.sensor_bias_lpm + self._noise(t)

        # --- sensor faults, applied to the READING only, never to the truth --
        if "dropout" in kinds:
            q_out = 0.0
        elif "stuck" in kinds:
            if self._stuck_value is None:
                self._stuck_value = q_out
            q_out = self._stuck_value
        else:
            self._stuck_value = None

        if "spike" in kinds:
            magnitude = max((f.magnitude for f in self._active_faults(t)
                             if f.kind == "spike"), default=1.0)
            q_out += magnitude * (1 if self.rng.random() > 0.5 else -1)

        q_in = max(0.0, q_in)
        q_out = max(0.0, q_out)
        q_branch = max(0.0, q_branch)

        # --- power ----------------------------------------------------------
        bus_v = s.bus_v_nominal + self.rng.gauss(0.0, s.bus_v_noise)
        current_ma = max(0.0, (s.pump_baseline_ma
                               + s.current_per_leak_lpm * total_leak
                               + demand * 4.0
                               + self.rng.gauss(0.0, s.current_noise_ma)))

        self._seq += 1
        payload = {
            # Manual/interactive streaming stamps wall-clock time so samples
            # advance monotonically like a real rig. Scripted playback keeps
            # scenario-relative time so a run is reproducible and scoreable.
            "ts": round(ts_override if ts_override is not None else self.base_ts + t, 3),
            "seq": self._seq,
            "device": f"mock-{s.id}",
            "mode": "mock",
            "flow": {
                "q_in_lpm": round(q_in, 3),
                "q_out_lpm": round(q_out, 3),
                "q_branch_lpm": round(q_branch, 3),
                **self._accumulate_pulses(q_in, q_out, q_branch),
            },
            "power": {
                "bus_v": round(bus_v, 3),
                "current_ma": round(current_ma, 1),
                "power_mw": round(bus_v * current_ma, 1),
            },
            "temp": {"water_c": round(self._water_temp(t), 2) if s.emit_temp else None},
            "actuators": {
                "pump1": True,
                "pump2": self._pump2_on(t),
                # The pinch valve is for isolation testing and is only moved on
                # explicit command — never autonomously, and never to make a leak.
                "servo_deg": 0,
            },
            "health": {
                "uptime_s": int(t),
                "wifi_rssi": -58 + int(self.rng.gauss(0, 2)),
                "free_heap": 184320,
            },
        }
        payload["vibration"] = self._vibration(total_leak, kinds)

        if s.emit_pressure:
            # SIMULATED. Mock mode only — the physical rig has no transducer, and
            # the live firmware publishes no such field. Computed from the same
            # q_in and total_leak that drive flow and current above, so the three
            # channels are coherent by construction.
            payload["pressure"] = {
                "bar": round(self._simulated_pressure(q_in, total_leak), 4),
                # Never "measured", never "estimated".
                "source": "simulated",
                "is_simulated": True,
            }
        return payload

    def _accumulate_pulses(self, q_in, q_out, q_branch) -> dict:
        """Interrupt-driven counters, derived from the SAME K-factors the backend
        converts with — so stored counts and stored rates can never disagree."""
        self._pulses_in += int(q_in * self.k1 / 60)
        self._pulses_out += int(q_out * self.k2 / 60)
        self._pulses_branch += int(q_branch * self.k3 / 60)
        return {
            "pulses_in": self._pulses_in,
            "pulses_out": self._pulses_out,
            "pulses_branch": self._pulses_branch,
        }

    def _simulated_pressure(self, q_in: float, total_leak: float) -> float:
        """SIMULATED line pressure at the tee. Nothing here is measured.

        Physically coherent with flow and current in the same frame, which is the
        whole point — three channels that contradict each other are worse than
        one channel, because they teach a reviewer to distrust all of them.

        Two effects, both in the same direction for a leak:

          1. **Pump curve.** Head falls as throughput rises. A leak opens an
             extra path, total flow goes up, so the operating point slides down
             the curve.
          2. **Local sag at the tee.** Water escaping upstream of the gauge drops
             the pressure it sees, over and above the curve effect.

        The same `total_leak` drives the current shift in `sample_at`, so a leak
        that raises flow and lowers current necessarily also lowers pressure.
        They cannot disagree — they are computed from one number.
        """
        s = self.scenario
        pressure = (s.pressure_shutoff_bar
                    - s.pressure_curve_slope * max(0.0, q_in)
                    - s.pressure_per_leak_lpm * total_leak
                    + self.rng.gauss(0.0, s.pressure_noise_bar))
        return max(0.0, pressure)

    def _vibration(self, total_leak: float, kinds: set) -> dict:
        """Band energies from the on-device FFT.

        A leak jet raises band_mid strongly and the neighbouring bands weakly —
        which is why the detector keys on band_mid specifically rather than on
        overall RMS, and on the ratio to baseline rather than an absolute.

        Crucially, a flow-meter dropout does NOT move this at all: no water
        actually escaped. That asymmetry is what lets the plausibility guard tell
        an instrument fault from a burst pipe.
        """
        s = self.scenario
        if not s.emit_vibration:
            # No accelerometer fitted. Nulls rather than zeros, mirroring what
            # the firmware publishes: zero is a reading from a quiet pipe,
            # absent is no sensor at all, and the two must not collapse.
            return {"rms": None, "band_low": None, "band_mid": None, "band_high": None,
                    "piezo_rms": None, "piezo_centroid_hz": None}
        del kinds  # sensor faults are flow-meter faults; they do not alter the pipe's noise

        noise = lambda: self.rng.gauss(0.0, s.vib_noise)

        # A leak raises band_mid strongly and its neighbours only weakly. That
        # DISPROPORTION is the signal — it is what makes spectral_tilt
        # (band_mid / band_low) informative and why the detector keys on band_mid
        # rather than overall RMS.
        band_mid = max(0.0, s.vib_baseline_mid + s.vib_per_leak_lpm * total_leak + noise())
        band_low = max(0.0, 0.012 + 0.004 * total_leak + noise())
        band_high = max(0.0, 0.020 + 0.010 * total_leak + noise())

        # Cavitation burst: loud, broadband, and NO leak behind it. Air coming
        # out of solution at the pump inlet does this. It raises every band at
        # once — unlike a leak, which tilts the spectrum — so the persistence
        # requirement and spectral_tilt are what tell them apart. A mock corpus
        # without these would overstate precision, because the acoustic channel's
        # single biggest false-positive source would be missing.
        if self.rng.random() < s.cavitation_burst_probability:
            gain = s.cavitation_burst_gain
            band_low *= gain
            band_mid *= gain
            band_high *= gain

        # Per-run mounting coupling, applied to every band equally. Absolute
        # levels shift run to run; ratios do not.
        band_low *= self._mount_gain
        band_mid *= self._mount_gain
        band_high *= self._mount_gain

        vib = {
            "rms": round(math.sqrt(band_low ** 2 + band_mid ** 2 + band_high ** 2), 6),
            "band_low": round(band_low, 6),
            "band_mid": round(band_mid, 6),
            "band_high": round(band_high, 6),
            "piezo_rms": None,
            "piezo_centroid_hz": None,
        }

        if s.emit_piezo:
            # The piezo reaches higher frequencies than the MPU6050, so a leak
            # raises both its amplitude and its centroid. NOTE the centroid is a
            # slope-weighted zero-crossing proxy in firmware, not calibrated Hz —
            # modelled the same way here so mock and rig agree in character.
            vib["piezo_rms"] = round(max(0.0, (0.015 + 0.012 * total_leak + noise())
                                         * self._mount_gain), 6)
            vib["piezo_centroid_hz"] = round(85.0 + 45.0 * min(1.0, total_leak / 1.5)
                                             + self.rng.gauss(0, 3), 1)
        return vib

    # --- streaming --------------------------------------------------------
    def stream(self, step_sec: float = 1.0) -> Iterator[dict]:
        t = 0.0
        while t <= self.scenario.duration_sec:
            yield self.sample_at(t)
            t += step_sec

    def generate_all(self, step_sec: float = 1.0) -> list:
        return list(self.stream(step_sec))

    def ground_truth_events(self) -> list:
        """Absolute-time leak windows in the same shape `leak_events` uses.

        These are the mock's equivalent of an operator logging a physical clamp
        opening: what the rig was *set* to leak, never what a detector thought.
        """
        return [
            {
                "open_ts": self.base_ts + l.start_sec,
                "close_ts": self.base_ts + l.end_sec,
                "tee_id": l.tee_id,
                "leak_lpm": l.rate_lpm,
                "clamp_turns": None,
                "demand_mode": self.scenario.demand_mode,
                "location_node": l.location,
                "is_ground_truth": True,
                "source": "generator",
                "notes": f"Mock scenario '{self.scenario.id}'"
                         + (f" (ramp {l.ramp_sec:.0f}s)" if l.ramp_sec else ""),
            }
            for l in self.scenario.leaks
        ]
