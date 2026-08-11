# MongoDB Data Model

Live rig data and generated mock data are stored in separate databases:

- `jal_netra_live` (`MONGO_DB_LIVE`)
- `jal_netra_mock` (`MONGO_DB_MOCK`)

Every repository resolves the active database through `backend/repositories/db.py`
and stamps persisted records with `mode`. The examples below omit MongoDB's
`_id` unless it is relevant.

## `telemetry`

One validated sensor sample after DTO normalization:

```json
{
  "mode": "live",
  "ts": 1754131200.123,
  "seq": 4471,
  "device": "esp32-rig-01",
  "run_id": "RUN_20260811_120000",
  "flow": {
    "q_in_lpm": 4.812,
    "q_out_lpm": 4.655,
    "q_branch_lpm": 2.104,
    "pulses_in": 361,
    "pulses_out": 349,
    "pulses_branch": 158
  },
  "power": { "bus_v": 11.94, "current_ma": 842.3, "power_mw": 10056.0 },
  "vibration": {
    "rms": 0.031,
    "band_low": 0.12,
    "band_mid": 0.44,
    "band_high": 0.08,
    "piezo_rms": null,
    "piezo_centroid_hz": null
  },
  "temp": { "water_c": 27.4 },
  "actuators": { "pump1": true, "pump2": false, "servo_deg": 0 },
  "health": { "uptime_s": 4471, "wifi_rssi": -58, "free_heap": 184320 },
  "source": "live"
}
```

There is no pressure transducer or leak solenoid in the physical contract.
Ground truth is stored separately, so detector output is never reused as truth.

## `leak_events`

Operator-recorded physical leak windows use `start_ts`/`stop_ts`; calibrated
tee records may use the equivalent `open_ts`/`close_ts` shape. Scoring
normalizes both.

```json
{
  "mode": "live",
  "run_id": "RUN_20260811_120000",
  "start_ts": 1786420805.2,
  "stop_ts": 1786420835.6,
  "location_node": "Branch_A",
  "severity_lpm": 1.25,
  "is_ground_truth": true,
  "source": "operator",
  "notes": "Clamp A opened to calibrated position"
}
```

## `detections`

The complete explainable response from `build_response`: timestamp, residual,
likelihood, confidence tier, zone, evidence, contributing methods, false-positive
warning, fusion result, optional sensor-fault explanation, and `run_id`.

## `experiment_runs`

```json
{
  "run_id": "RUN_20260811_120000",
  "operator": "operator",
  "date": "2026-08-11",
  "location": "Branch_A",
  "leak_size_lpm": 1.25,
  "pump_mode": "Constant 12V",
  "notes": "Physical demo run",
  "start_ts": 1786420800.0,
  "stop_ts": 1786420860.0,
  "duration_sec": 60.0,
  "status": "COMPLETED",
  "source": "live"
}
```

## `alerts`

One incident aggregates consecutive alarming samples and tracks operator
disposition (`ACTIVE`, `RESOLVED`, or `FALSE_POSITIVE`), evidence, peak leak
rate, impact, work-order summary, WhatsApp notification metadata, and savings.

## `work_orders`

Contains the selected CP-SAT schedule: alert/leak id, localized node, severity,
priority, assigned crew, scheduled start, estimated duration, status, and impact.

## `events`

Optional operational audit entries from `SystemEventLogger`, with `ts`,
`category`, `message`, and free-form `metadata`.
