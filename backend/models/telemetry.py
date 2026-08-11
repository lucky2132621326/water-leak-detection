"""Telemetry Data Transfer Objects — the contract between firmware, backend and UI.

The wire format is defined in docs/MQTT_SPEC.md (spec Part G) and is **nested**.
The previous flat format is gone: the ESP32 is being reflashed for this rig, so
nothing emits it, and keeping a parser for a format nothing produces is dead code
that will mislead whoever reads it next.

Two fields are deliberately absent:

  * **`pressure_bar`** — this rig has no pressure transducer of any kind. There
    is no estimated substitute either: a flow-derived "pressure" is a restatement
    of the residual, and printing it next to real measurements invites it to be
    read as independent evidence.
  * **`solenoid_state`** — there is no solenoid. Leaks are opened by hand on a
    worm-drive clamp, so ground truth is an operator-logged window in
    `leak_events`, not a per-sample flag.

Two fields are nullable because their hardware is optional, and detection must
degrade rather than break when they are missing:

  * **`temp.water_c`** — DS18B20 will not enumerate without its 4.7k pull-up.
  * **`vibration.piezo_*`** — the piezo disc is a secondary acoustic channel.
    The MPU6050 carries the acoustic detector on its own; the piezo only
    corroborates at frequencies the accelerometer cannot reach.
"""
from dataclasses import dataclass, field
from typing import Optional

from backend.mode import MODE_LIVE


@dataclass
class FlowData:
    q_in_lpm: float = 0.0
    q_out_lpm: float = 0.0
    q_branch_lpm: float = 0.0
    #: Raw pulse counts, published alongside the converted rates and never
    #: derived from them. If a K-factor is later recalibrated, every historical
    #: experiment can be recomputed from these instead of re-run physically.
    pulses_in: int = 0
    pulses_out: int = 0
    pulses_branch: int = 0


@dataclass
class PowerData:
    #: Bus voltage at the INA219, high-side on P1's 12V line. Named `bus_v` to
    #: match the sensor's own terminology and the wire format.
    bus_v: float = 12.0
    current_ma: float = 0.0
    power_mw: float = 0.0


@dataclass
class VibrationData:
    """Summary statistics from the on-device FFT.

    The ESP32 samples the MPU6050 in bursts (512 samples @ 500 Hz) and publishes
    band energies rather than the waveform — acoustic data cannot be streamed at
    1 Hz. This is bandwidth reduction, not detection: every threshold and every
    decision stays in the Python backend.

    Leak jet energy concentrates in `band_mid` (50-150 Hz). Absolute values are
    meaningless across rigs and pump duties, so the detector works on the ratio
    to a clean running baseline.
    """
    #: False when no MPU6050 is fitted. Distinct from all-zero bands, which is a
    #: legitimate reading from a quiet pipe.
    has_accelerometer: bool = True
    rms: float = 0.0
    band_low: float = 0.0      # 10-50 Hz
    band_mid: float = 0.0      # 50-150 Hz — leak jet energy lives here
    band_high: float = 0.0     # 150-250 Hz
    #: None when no piezo disc is fitted. Optional hardware; the accelerometer
    #: carries the channel alone if it is absent.
    piezo_rms: Optional[float] = None
    piezo_centroid_hz: Optional[float] = None

    @property
    def has_piezo(self) -> bool:
        return self.piezo_rms is not None


@dataclass
class TempData:
    """Reservoir water temperature. Not a detection channel.

    Feeds a K-factor correction: flow-meter calibration drifts with water
    viscosity, and over a two-hour run the pump warms the reservoir enough to
    walk the residual baseline. Without this correction that drift looks exactly
    like a slowly worsening leak.
    """
    water_c: Optional[float] = None   # None = probe absent or not enumerated


@dataclass
class ActuatorData:
    #: Relays are ACTIVE-LOW and initialised OFF at boot, before WiFi (Part H).
    #: False is therefore the correct default: a rig we have not heard from is
    #: not pumping.
    pump1: bool = False
    pump2: bool = False
    #: MG996R pinch valve on Branch A. 0 = open, 90 = pinched closed. Used for
    #: step-test isolation, never for leak creation.
    servo_deg: int = 0


@dataclass
class HealthData:
    uptime_s: int = 0
    wifi_rssi: int = -60
    free_heap: int = 180000


@dataclass
class TelemetryDTO:
    ts: float
    seq: int
    device: str = "esp32-rig-01"
    #: Which store this sample belongs to. Travels with the sample so a document
    #: read in isolation still says what it is.
    mode: str = MODE_LIVE
    flow: FlowData = field(default_factory=FlowData)
    power: PowerData = field(default_factory=PowerData)
    vibration: VibrationData = field(default_factory=VibrationData)
    temp: TempData = field(default_factory=TempData)
    actuators: ActuatorData = field(default_factory=ActuatorData)
    health: HealthData = field(default_factory=HealthData)

    @classmethod
    def from_dict(cls, data: dict) -> 'TelemetryDTO':
        flow_d = data.get("flow") or {}
        power_d = data.get("power") or {}
        vib_d = data.get("vibration") or {}
        temp_d = data.get("temp") or {}
        act_d = data.get("actuators") or {}
        health_d = data.get("health") or {}

        return cls(
            ts=float(data.get("ts", 0.0)),
            seq=int(data.get("seq", 0)),
            device=str(data.get("device", "esp32-rig-01")),
            mode=str(data.get("mode", MODE_LIVE)),
            flow=FlowData(
                q_in_lpm=float(flow_d.get("q_in_lpm", 0.0)),
                q_out_lpm=float(flow_d.get("q_out_lpm", 0.0)),
                q_branch_lpm=float(flow_d.get("q_branch_lpm", 0.0)),
                pulses_in=int(flow_d.get("pulses_in", 0)),
                pulses_out=int(flow_d.get("pulses_out", 0)),
                pulses_branch=int(flow_d.get("pulses_branch", 0)),
            ),
            power=PowerData(
                bus_v=float(power_d.get("bus_v", 12.0)),
                current_ma=float(power_d.get("current_ma", 0.0)),
                power_mw=float(power_d.get("power_mw", 0.0)),
            ),
            vibration=VibrationData(
                # A rig with no MPU6050 omits the block, or sends nulls. Either
                # way the bands read 0.0 and `has_accelerometer` is False — the
                # detector checks that flag rather than inferring absence from a
                # zero, which is a legitimate reading on a silent pipe.
                has_accelerometer=any(
                    vib_d.get(k) is not None for k in ("rms", "band_low", "band_mid", "band_high")
                ),
                rms=_optional_float(vib_d.get("rms")) or 0.0,
                band_low=_optional_float(vib_d.get("band_low")) or 0.0,
                band_mid=_optional_float(vib_d.get("band_mid")) or 0.0,
                band_high=_optional_float(vib_d.get("band_high")) or 0.0,
                # Absent and null both mean "no piezo fitted". Never coerced to
                # 0.0, which would read as a silent microphone rather than none.
                piezo_rms=_optional_float(vib_d.get("piezo_rms")),
                piezo_centroid_hz=_optional_float(vib_d.get("piezo_centroid_hz")),
            ),
            temp=TempData(water_c=_optional_float(temp_d.get("water_c"))),
            actuators=ActuatorData(
                pump1=bool(act_d.get("pump1", False)),
                pump2=bool(act_d.get("pump2", False)),
                servo_deg=int(act_d.get("servo_deg", 0) or 0),
            ),
            health=HealthData(
                uptime_s=int(health_d.get("uptime_s", 0)),
                wifi_rssi=int(health_d.get("wifi_rssi", -60)),
                free_heap=int(health_d.get("free_heap", 180000)),
            ),
        )


def _optional_float(value):
    """None stays None; anything unparseable becomes None rather than 0.0.

    The distinction matters: 0.0 is a reading, None is the absence of a sensor.
    Collapsing the two would make a missing piezo look like a silent one.
    """
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
