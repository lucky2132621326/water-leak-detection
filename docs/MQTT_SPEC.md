# MQTT Interface Contract

`HARDWARE_INTEGRATION_SPEC.md` and the firmware implement the same contract.
MQTT stays on the isolated rig network and is never part of the public tunnel.

## Broker and credentials

- TCP port: `1883`
- Device account: publish telemetry/status; subscribe commands
- Backend account: subscribe telemetry/status; publish commands
- Telemetry retain: `false`
- Status retain: `true`
- Last Will: retained JSON status with `OFFLINE`

Credentials belong in the git-ignored `firmware/src/secrets.h` and root `.env`.

## `rig/telemetry`

Published once per second by `esp32-rig-01` using the nested schema below.
Telemetry is sent at QoS 0 by PubSubClient; each sample carries raw cumulative
pulse counts so gaps and recalibration can be handled downstream.

```json
{
  "ts": 1754131200.123,
  "device": "esp32-rig-01",
  "mode": "live",
  "clock_synced": true,
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
  "vibration": {
    "rms": 0.031,
    "band_low": 0.12,
    "band_mid": 0.44,
    "band_high": 0.08,
    "piezo_rms": 0.017,
    "piezo_centroid_hz": 312.0
  },
  "temp": { "water_c": 27.4 },
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

Unavailable acoustic or temperature sensors publish JSON `null`, never a fake
zero. An unsynchronised ESP32 publishes `ts: 0` and `clock_synced: false`; the
backend substitutes server receive time and exposes a substitution counter.

Raw pulse counts are mandatory so historical flow can be recalculated after
K-factor calibration. The backend accepts the former flat packet only as a
compatibility path.

There is no pressure transducer on the current rig. The backend labels any
flow-derived pressure value as `estimated`; mock datasets may carry authored
logged values.

## `rig/cmd`

Supervised commands may change one or more listed fields. Missing fields retain
their current state, while a payload with no supported field is rejected.

```json
{ "pump1": true, "pump2": false, "servo_deg": 90 }
```

Commands never originate from the public judge dashboard. Firmware enforces a
30-second command watchdog and a continuous-runtime ceiling locally.

## `rig/status`

Retained device presence and health. The MQTT Last Will publishes an `OFFLINE`
object if the device connection drops unexpectedly.

```json
{
  "device": "esp32-rig-01",
  "wifi_rssi": -58,
  "uptime_sec": 4471,
  "heap_free": 184320,
  "status": "online"
}
```
