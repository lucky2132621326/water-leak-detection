# MQTT SPECIFICATION

## Broker Configuration
- **Default Port**: 1883 (TCP)
- **Quality of Service (QoS)**: 1 (At least once delivery)
- **Retain Flag**: False for telemetry, True for status

## Topics

### 1. `rig/telemetry`
Published by ESP32 every 1000ms.

#### JSON Payload Schema:
```json
{
  "ts": 1722686947,
  "device_id": "esp32_rig_01",
  "q_in_lpm": 5.20,
  "q_out_lpm": 5.15,
  "q_branch_lpm": 0.00,
  "current_ma": 420.5,
  "voltage_v": 12.1,
  "pressure_bar": 2.48,
  "raw_pulses_in": 2368,
  "raw_pulses_out": 2345,
  "solenoid_state": false
}
```

> **`pressure_bar`** is published from the analog transducer on `PIN_PRESSURE`
> (GPIO 36) and tagged `"source": "measured"` downstream.
>
> The key is **omitted entirely** when the transducer reads unhealthy — output
> below its 0.5 V floor, meaning disconnected or unpowered. Omission is
> deliberate: publishing `0.0` would look like a catastrophic pressure collapse
> and could raise a false alarm. On omission the backend falls back to
> `backend/utils/pressure_estimate.py`, tagging the value `"source": "estimated"`.
>
> Replay/synthetic datasets carry authored values tagged `"source": "logged"`.
>
> The pressure-drop detector scores **only** `"measured"` readings. Estimated
> pressure is derived from the same flow numbers the mass-balance detector
> already uses, so scoring it would manufacture agreement between two views of
> one measurement rather than provide independent corroboration.

### 2. `rig/cmd`
Commands sent to the ESP32.

#### Example Command Payload:
```json
{
  "cmd": "SET_VALVE",
  "valve_id": "leak_valve_1",
  "state": "OPEN",
  "ts": 1722686950
}
```

### 3. `rig/status`
Health status published on boot and periodically.

```json
{
  "device_id": "esp32_rig_01",
  "wifi_rssi": -62,
  "uptime_sec": 3450,
  "heap_free": 184520,
  "status": "ONLINE"
}
```
