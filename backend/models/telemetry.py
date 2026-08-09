"""Canonical telemetry data transfer objects.

The ESP32 intentionally publishes a compact, flat JSON payload to conserve
memory. Stored replay documents use the richer nested representation.  This
module is the single compatibility boundary between both shapes so the
detection pipeline always receives the same typed values.
"""
from dataclasses import dataclass, field

@dataclass
class FlowData:
    q_in_lpm: float = 0.0
    q_out_lpm: float = 0.0
    q_branch_lpm: float = 0.0
    pulses_in: int = 0
    pulses_out: int = 0
    pulses_branch: int = 0

@dataclass
class PowerData:
    voltage: float = 12.0
    current_ma: float = 400.0

@dataclass
class ActuatorData:
    pump1: bool = True
    pump2: bool = False
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
    device_id: str = "unknown"
    flow: FlowData = field(default_factory=FlowData)
    power: PowerData = field(default_factory=PowerData)
    actuators: ActuatorData = field(default_factory=ActuatorData)
    health: HealthData = field(default_factory=HealthData)

    @classmethod
    def from_dict(cls, data: dict) -> 'TelemetryDTO':
        flow_d = data.get("flow") if isinstance(data.get("flow"), dict) else {}
        power_d = data.get("power") if isinstance(data.get("power"), dict) else {}
        act_d = data.get("actuators") if isinstance(data.get("actuators"), dict) else {}
        health_d = data.get("health") if isinstance(data.get("health"), dict) else {}

        # Compact firmware payload aliases. Nested values win when both are
        # present because that is the canonical stored/replay representation.
        solenoid_open = bool(data.get("solenoid_state", False))

        return cls(
            ts=data.get("ts", 0.0),
            seq=data.get("seq", 0),
            device_id=str(data.get("device_id", data.get("device", "unknown"))),
            flow=FlowData(
                q_in_lpm=float(flow_d.get("q_in_lpm", data.get("q_in_lpm", 0.0))),
                q_out_lpm=float(flow_d.get("q_out_lpm", data.get("q_out_lpm", 0.0))),
                q_branch_lpm=float(flow_d.get("q_branch_lpm", data.get("q_branch_lpm", 0.0))),
                pulses_in=int(flow_d.get("pulses_in", data.get("raw_pulses_in", 0))),
                pulses_out=int(flow_d.get("pulses_out", data.get("raw_pulses_out", 0))),
                pulses_branch=int(flow_d.get("pulses_branch", data.get("raw_pulses_branch", 0)))
            ),
            power=PowerData(
                voltage=float(power_d.get("voltage", power_d.get("bus_v", data.get("voltage_v", 12.0)))),
                current_ma=float(power_d.get("current_ma", data.get("current_ma", 400.0)))
            ),
            actuators=ActuatorData(
                pump1=bool(act_d.get("pump1", data.get("pump_on", True))),
                pump2=bool(act_d.get("pump2", False)),
                servo_deg=int(act_d.get("servo_deg", data.get("servo_deg", 45 if solenoid_open else 0)))
            ),
            health=HealthData(
                uptime_s=int(health_d.get("uptime_s", data.get("uptime_sec", 0))),
                wifi_rssi=int(health_d.get("wifi_rssi", data.get("wifi_rssi", -60))),
                free_heap=int(health_d.get("free_heap", data.get("heap_free", 180000)))
            )
        )
