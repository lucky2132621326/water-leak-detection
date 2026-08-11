# MQTT Interface Contract

The hardware-owner contract in `HARDWARE_INTEGRATION_SPEC.md` is the source of
truth. Firmware and the mock publisher emit the same nested payload.

## Broker

- TCP port: `1883`
- Telemetry QoS: `1`
- Telemetry retain: `false`
- Status QoS: `1`
- Status retain: `true`

## `rig/telemetry`

Published once per second by `esp32-rig-01`.

```json
{
  "ts": 1754131200.123,
  "seq": 4471,
  "device": "esp32-rig-01",
  "flow": {
    "q_in_lpm": 4.812,
    "q_out_lpm": 4.655,
    "q_branch_lpm": 2.104,
    "pulses_in": 361,
    "pulses_out": 349,
    "pulses_branch": 158
  },
  "power": {
    "bus_v": 11.94,
    "current_ma": 842.3,
    "power_mw": 10056.0
  },
  "actuators": {
    "pump1": true,
    "pump2": false,
    "servo_deg": 0
  },
  "health": {
    "uptime_s": 4471,
    "wifi_rssi": -58,
    "free_heap": 184320
  }
}
```

Raw pulse counts are mandatory so historical flow can be recalculated after
K-factor calibration. The backend also accepts the former flat packet as a
temporary compatibility path; new firmware must publish the nested schema.

There is no pressure transducer on the current rig. The backend tags any
derived pressure value as `estimated`; replay data may contain a logged value.

## `rig/cmd`

Supervised rig command. All fields are required; incomplete commands are
rejected by firmware.

```json
{ "pump1": true, "pump2": false, "servo_deg": 90 }
```

Commands never originate from the public decision-support dashboard. Firmware
enforces a 30-second command watchdog and a continuous-runtime ceiling locally.

## `rig/status`

Retained device presence and health. MQTT Last Will publishes `OFFLINE` if the
device connection drops unexpectedly.

```json
{
  "device": "esp32-rig-01",
  "wifi_rssi": -58,
  "uptime_sec": 4471,
  "heap_free": 184320,
  "status": "ONLINE"
}
```
