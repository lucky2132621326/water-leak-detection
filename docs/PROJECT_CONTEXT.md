# Project Context

## Agent rules

1. Reuse existing modules; do not create parallel implementations.
2. Update `CHANGELOG.md` when behavior changes.
3. Update `MQTT_SPEC.md` and `DATABASE_SCHEMA.md` with their contracts.
4. Do not present mock, estimated, or decorative data as physical evidence.
5. Detection output is indicative and requires field verification.
6. Never expose MQTT, MongoDB, FastAPI, credentials, or mutation controls through
   the public judge tunnel.

## Product scope

Jal Netra is a single-team hardware diagnostic dashboard for one physical water
rig. It is not a public multi-tenant SaaS: there are no end-user accounts,
payments, public content pages, or remote valve-control workflows.

The system detects abnormal flow balance, pump-current changes, cumulative
drift, minimum-night-flow deviations, and optional pipe-acoustic changes. It
localizes likely zones, explains evidence and confidence, produces incident and
work-order summaries, and keeps detector results separate from physical ground
truth.

## Current verified state

- Python suite: 153 tests plus 74 subtests passing.
- TypeScript check and production build passing.
- ESP32 firmware compiles successfully with PlatformIO / arduinoFFT 2.x.
- Judge boundary test confirms all public mutations return 403 while the local
  operator proxy remains authenticated and writable.
- Software paths are validated; physical sensors and thresholds still require
  bench calibration and a complete hardware rehearsal.

## Hardware contract

| Component | Interface |
|---|---|
| ESP32 DevKit V1 | Wi-Fi + MQTT |
| Flow 1 / inlet | GPIO 34, rising-edge interrupt |
| Flow 2 / outlet | GPIO 35, rising-edge interrupt |
| Flow 3 / Branch B | GPIO 32, rising-edge interrupt |
| INA219 | I²C SDA 21 / SCL 22, address 0x40 |
| MPU6050 | I²C SDA 21 / SCL 22, address 0x68 |
| Optional piezo | GPIO 33, ADC1 |
| DS18B20 | GPIO 4, 1-Wire with 4.7 kΩ pull-up |
| Supply pump relay | GPIO 25, active-low |
| Demand pump relay | GPIO 26, active-low |
| Branch A pinch servo | GPIO 27, separate servo supply |

The current rig has no pressure transducer and no leak solenoid. Dashboard
pressure is an explicitly labelled estimate and is not independent detection
evidence. Physical leaks are opened manually; operator-recorded time windows are
the live ground truth.

## Architecture

```text
ESP32 ── MQTT rig/telemetry + rig/status ──► MqttTelemetrySource
Mock scenario generator ───────────────────► MockTelemetrySource
                                             │
                                             ▼
                                  one TelemetryIngestor
                                             │
                  validate → DTO → detectors → plausibility → fusion
                              → localization → alerts/impact/reports
                                             │
                       jal_netra_live OR jal_netra_mock (MongoDB)
                                             │
                                      FastAPI :8001
                                             │ server-side API key
                                      Node operator :3000
                                      Node judge :3001 (read-only)
                                             │
                                  Cloudflare Quick Tunnel
                                  exposes only judge :3001
```

Exactly two operating modes exist: `mock` and `live`. They differ only at the
telemetry source; all validation and detection after ingestion is shared.
Offline benchmark scoring reuses the production pipeline but is not an
operating mode.

## Core modules

- `backend/ingestion/`: shared ingestor plus mock/live source adapters.
- `backend/detectors/`: mass balance, current signature, MNF, CUSUM, acoustic,
  and the cross-channel plausibility guard.
- `backend/fusion/`, `backend/localization/`, `backend/alerts/`:
  explainable decision and incident lifecycle.
- `backend/benchmark/`, `backend/analytics/`, `backend/reports/`: computed
  performance evidence from stored runs and logged leak windows.
- `backend/scheduler/cp_sat_scheduler.py`: OR-Tools crew scheduling with an
  explicitly labelled fallback.
- `backend/notifications/whatsapp.py`: optional Twilio WhatsApp notification;
  failures never break detection.
- `firmware/src/`: nested MQTT telemetry, retained status/Last Will, authenticated
  broker connection, local pump watchdog, and sensor acquisition.
- `server.ts`: server-side API-key proxy and operator/judge policy boundary.

## Storage and contracts

MongoDB uses physically separate `jal_netra_live` and `jal_netra_mock`
databases, selected centrally by `backend/repositories/db.py`. See
`DATABASE_SCHEMA.md`.

MQTT topics are `rig/telemetry`, `rig/status`, and `rig/cmd`. The broker is bound
only to loopback and/or the dedicated rig interface, with separate device and
backend accounts. See `MQTT_SPEC.md`.

## Remaining hardware work

1. Wire and validate each sensor using the serial-test firmware.
2. Calibrate every flow-meter K factor and the clean residual bias/sigma.
3. Establish clean acoustic and pump-current baselines on the assembled rig.
4. Provision Mosquitto ACLs and copy local credentials into git-ignored `.env`
   and `firmware/src/secrets.h`.
5. Rehearse mock fallback, live transition, manual leak ground truth, detection,
   localization, alert/report generation, ESP32 disconnect, and recovery.
