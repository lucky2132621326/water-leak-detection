"""Telemetry Data Transfer Objects — the contract between firmware, backend and UI.

The wire format is defined in docs/MQTT_SPEC.md (spec Part G) and is **nested**.
New firmware emits the nested format. The parser also accepts the former flat
field names as a temporary stored-data compatibility path; detection receives
the same DTO either way.

Two fields are deliberately absent:

  * **`pressure_bar`** — the LIVE rig has no pressure transducer of any kind, and
    the firmware publishes no such field. There is no estimated substitute
    either: a flow-derived "pressure" is a restatement of the residual, and
    printing it beside real measurements invites it to be read as independent
    evidence. Mock mode carries a separate, explicitly SIMULATED pressure block
    (see `SimulatedPressure` below) which live telemetry never populates.
  * **`solenoid_state`** — there is no solenoid. Leaks are opened by hand on a
    worm-drive clamp, so ground truth is an operator-logged window in
    `leak_events`, not a per-sample flag.

Three fields are nullable because their hardware is optional, and detection must
degrade rather than break when they are missing:

  * **`power.bus_v/power_mw`** — ACS712 measures current only; voltage and
    computed power stay absent while INA219 is not fitted.
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
    #: Bus voltage when INA219 is fitted. ACS712 does not provide this field.
    bus_v: Optional[float] = None
    current_ma: Optional[float] = None
    power_mw: Optional[float] = None

    @property
    def voltage(self) -> Optional[float]:
        """Backward-compatible name used by stored replay/report code."""
        return self.bus_v


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
class SimulatedPressure:
    """MOCK ONLY. Generated pressure, never a sensor reading.

    Lives in its own type with `is_simulated` baked in rather than as a bare
    `pressure_bar` float, so a value cannot be read out of the DTO without the
    caveat attached. `source` is always "simulated" — never "measured", never
    "estimated". Live telemetry leaves this None and the live DetectorManager
    builds no pressure detector to consume it.
    """
    bar: Optional[float] = None
    source: str = "simulated"
    is_simulated: bool = True

    @property
    def is_present(self) -> bool:
        return self.bar is not None


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
    #: MOCK ONLY, and None in live without exception — the firmware publishes no
    #: pressure field, so a live payload has no key for this to parse.
    pressure: Optional[SimulatedPressure] = None

    @property
    def device_id(self) -> str:
        return self.device

    @classmethod
    def from_dict(cls, data: dict) -> 'TelemetryDTO':
        flow_d = data.get("flow") if isinstance(data.get("flow"), dict) else {}
        power_d = data.get("power") if isinstance(data.get("power"), dict) else {}
        vib_d = data.get("vibration") or {}
        temp_d = data.get("temp") or {}
        act_d = data.get("actuators") or {}
        health_d = data.get("health") or {}

        return cls(
            ts=float(data.get("ts", 0.0)),
            seq=int(data.get("seq", 0)),
            device=str(data.get("device", data.get("device_id", "esp32-rig-01"))),
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
                bus_v=_optional_float(power_d.get("bus_v", power_d.get("voltage"))),
                current_ma=_optional_float(power_d.get("current_ma")),
                power_mw=_optional_float(power_d.get("power_mw")),
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
            # Present only when the mock generator emitted it. A live payload has
            # no `pressure` key, so this stays None and nothing downstream can
            # surface a pressure value for a real rig.
            pressure=(SimulatedPressure(
                bar=_optional_float((data.get("pressure") or {}).get("bar")),
                source=(data.get("pressure") or {}).get("source", "simulated"),
                is_simulated=True,
            ) if data.get("pressure") else None),
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

    def to_dict(self) -> dict:
        """Return the canonical nested telemetry document used for storage/UI."""
        return {
            "ts": self.ts,
            "seq": self.seq,
            "device": self.device,
            "device_id": self.device,
            "mode": self.mode,
            "flow": {
                "q_in_lpm": self.flow.q_in_lpm,
                "q_out_lpm": self.flow.q_out_lpm,
                "q_branch_lpm": self.flow.q_branch_lpm,
                "pulses_in": self.flow.pulses_in,
                "pulses_out": self.flow.pulses_out,
                "pulses_branch": self.flow.pulses_branch,
            },
            "power": {
                "bus_v": self.power.bus_v,
                "current_ma": self.power.current_ma,
                "power_mw": self.power.power_mw,
            },
            "vibration": {
                "rms": self.vibration.rms if self.vibration.has_accelerometer else None,
                "band_low": self.vibration.band_low if self.vibration.has_accelerometer else None,
                "band_mid": self.vibration.band_mid if self.vibration.has_accelerometer else None,
                "band_high": self.vibration.band_high if self.vibration.has_accelerometer else None,
                "piezo_rms": self.vibration.piezo_rms,
                "piezo_centroid_hz": self.vibration.piezo_centroid_hz,
            },
            "temp": {"water_c": self.temp.water_c},
            "pressure": ({
                "bar": self.pressure.bar,
                "source": "simulated",
                "is_simulated": True,
            } if self.pressure else None),
            "actuators": {
                "pump1": self.actuators.pump1,
                "pump2": self.actuators.pump2,
                "servo_deg": self.actuators.servo_deg,
            },
            "health": {
                "uptime_s": self.health.uptime_s,
                "wifi_rssi": self.health.wifi_rssi,
                "free_heap": self.health.free_heap,
            },
        }


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
