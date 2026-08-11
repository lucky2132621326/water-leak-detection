# PROJECT CONTEXT

> **AI AGENT INSTRUCTIONS**
> 1. Read `PROJECT_CONTEXT.md` before coding.
> 2. Do not create duplicate modules.
> 3. Reuse existing files whenever possible.
> 4. Update `PROJECT_CONTEXT.md` after changes.
> 5. Update `CHANGELOG.md` after changes.
> 6. Do not modify MQTT schema without updating `MQTT_SPEC.md`.
> 7. Do not modify database schema without updating `DATABASE_SCHEMA.md`.
> 8. Keep architecture simple.
> 9. Complete current phase before starting next phase.
> 10. Do not introduce new frameworks without justification.

---

## Hardware Status

> The table below used to claim ONLINE/WORKING status and a fixed IP that
> were never actually verified against physical hardware, and pins that
> don't match `firmware/src/config.h`. Corrected to the real pin map
> (`docs/HARDWARE_INTEGRATION_SPEC.md` v2) and an honest status: nothing
> here has been bench-verified in this repo yet.

| Component | Status | GPIO / Interface | Notes |
|---|---|---|---|
| **ESP32 DevKit V1** | NOT YET WIRED | WiFi / MQTT | No physical bring-up performed yet |
| **YF-S201 Flow Sensor #1 ($Q_{\text{in}}$)** | NOT YET WIRED | GPIO 34, interrupt RISING | `firmware/serial_test/serial_test.ino` is the first verification step |
| **YF-S201 Flow Sensor #2 ($Q_{\text{out}}$)** | NOT YET WIRED | GPIO 35, interrupt RISING | |
| **YF-S201 Flow Sensor #3 ($Q_{\text{branch}}$)** | NOT YET WIRED | GPIO 32, interrupt RISING | |
| **INA219 Power/Current Sensor** | NOT YET WIRED | I2C SDA 21 / SCL 22 @ 0x40 | Motor current load monitoring |
| **MPU6050 Accelerometer** | NOT YET WIRED | I2C SDA 21 / SCL 22 @ 0x68 | v2 addition — acoustic channel |
| **Piezo Disc** | NOT YET WIRED | GPIO 33, ADC1 | v2 addition — secondary acoustic channel |
| **DS18B20 Temperature Probe** | NOT YET WIRED | GPIO 4, 1-Wire (needs 4.7k pull-up) | v2 addition — K-factor temp compensation |
| **12V DC Pump #1 (P1, supply)** | NOT YET WIRED | Relay GPIO 25, active-LOW | |
| **12V DC Pump #2 (P2, demand)** | NOT YET WIRED | Relay GPIO 26, active-LOW | |
| **Servo MG996R Isolation Valve** | NOT YET WIRED | PWM GPIO 27, 50Hz LEDC | Branch A isolation; separate 5.6V rail |

No status LED in this revision — not wanted (see hardware spec section 3).

---

## Project Overview
- **Name**: Water Leak Detection System (Hardware-In-The-Loop Bench & Analytics Workbench)
- **Scope**: 2-week student project for 5 team members.
- **Goal**: High-reliability physical rig and digital twin for real-time water pipeline leak detection, multi-algorithm sensor fusion, branch isolation, and automated crew work order scheduling.
- **Current Phase**: Rebuilding the real pipeline ahead of the Aug 8 hackathon-ready checkpoint — an audit on 2026-08-05 found most of "Phase 1-3 Completed" below was dashboard-mock/scaffolding, not wired end-to-end. See `docs/CHANGELOG.md` [2026-08-05] for what was actually fixed.
- **Current Status**: Real MongoDB persistence, MNF detection, and a shared live/replay `DetectionPipeline` now exist and are wired through `backend/api_server.py` -> `server.ts` (proxy) -> dashboard. Firmware was rewritten with real WiFi/MQTT/sensor code but is untested against physical hardware in this environment. Still needed before demo: run against a real Mosquitto broker + MongoDB instance + the physical rig; flash and bench-test firmware; verify the Azure OpenAI summary path end-to-end (falls back to a template if unset).
- **Last Updated**: 2026-08-05

---

---

## System Architecture Summary
```text
ESP32 (Telemetry Rig)
  ↓ [MQTT / rig/telemetry, rig/status, rig/cmd]
Mosquitto Broker
  ↓
backend/mqtt/subscriber.py (live) ── backend/replay/replay_runner.py (replay)
  ↓                                          ↓
        backend/pipeline.py — DetectionPipeline (shared by both)
  ├── Detectors: Mass Balance, Current Signature, MNF, CUSUM, Acoustic
  ├── Fusion Engine (weighted + independent-agreement bonus)
  ├── Localization Service (isolation-test evidence, not actuator-state shortcut)
  └── Response Builder (likelihood, evidence, work-order summary)
  ↓
MongoDB (water_leak_detection) + independent JSONL live-data log
  ↓
backend/api_server.py (FastAPI) → server.ts (thin proxy) → React dashboard
```

---

## Completed Features (software — none bench-verified against real hardware yet)
- [x] **Detection pipeline (5 channels)**: Mass Balance (3σ), Current Signature, MNF, CUSUM, Acoustic (MPU6050+piezo, v2) — `backend/pipeline.py`, `backend/detectors/`.
- [x] **Weighted fusion + independent-agreement bonus**: `backend/fusion/fusion_engine.py`.
- [x] **Branch localization via real isolation-test evidence** (not just servo-state shortcut): `backend/localization/localization_service.py` + `branch_analyzer.py`.
- [x] **MongoDB persistence**: `telemetry`, `detections`, `leak_events`, `experiment_runs`, `work_orders`, `events` collections — `backend/repositories/`.
- [x] **Replay engine**: one real seeded run (`RUN_001`, not RUN_001-012 — see `backend/replay/seed_runs.py`) scored with real precision/recall/F1/latency, not hardcoded.
- [x] **Ground-truth leak logging**: `/api/ground-truth/start|stop|status`, replacing software leak injection.
- [x] **Work order dispatch**: `backend/scheduler/work_order_scheduler.py` — plain round-robin by crew index, NOT a CP-SAT/OR-Tools constraint solve (renamed from the misleading `cp_sat_scheduler.py`).
- [x] **Impact analysis, Alert Center, experiment reports**: `backend/impact/`, `backend/alerts/`, `backend/reports/`.

## Explicitly decorative / not real (do not present as working)
- `simulation/wntr_model.py` and `/api/simulation/wntr` — hardcoded sine-wave curve, not a WNTR/EPANET hydraulic solve. Not wired into the dashboard nav.
- `src/components/AnalyticsView.tsx` — 100% hardcoded fake ROC/precision numbers, no fetch calls. Intentionally hidden from the sidebar.
- `src/components/SettingsView.tsx` — Save/Self-Test buttons are local-state theater, no backend calls. Intentionally hidden from the sidebar.

---

## Pending Features / Next Tasks
- [ ] Firmware `main.cpp`: MPU6050 burst+FFT sampling, piezo ADC, DS18B20 1-Wire read (hardware spec v2 task 2) — not started.
- [ ] Physical bring-up: `firmware/serial_test/serial_test.ino` is the first milestone, not yet run against real hardware.
- [ ] Validation scenario matrix beyond the single seeded `RUN_001` (multiple leak sizes/zones/onset times, no-leak controls).
- [ ] Authentication/authorization on mutating endpoints (mode switch, work-order dispatch, alert disposition).

---

## Database Schema Overview (MongoDB — not SQLite; see Decision #001)
- `telemetry`: `_id`, `ts`, `seq`, `device_id`, `run_id`, `flow{q_in_lpm,q_out_lpm,q_branch_lpm,pulses_in,pulses_out,pulses_branch}`, `power{voltage,current_ma}`, `actuators{pump1,pump2,servo_deg}`, `health{...}`, `vibration{rms,band_low,band_mid,band_high,piezo_rms,piezo_centroid_hz}` (v2, nullable), `temp{water_c}` (v2, nullable), `pressure_bar`, `pressure_source`
- `leak_events`: `_id`, `start_ts`, `stop_ts`, `location_node`, `severity_lpm`, `run_id`, `is_ground_truth`, `notes`, `metadata`
- `detections`: full `response_builder.py` output per sample (`likelihood_score`, `zone`, `evidence`, `detectors`, `fusion`, etc.), `run_id`
- `experiment_runs`: `run_id`, `operator`, `date`, `leak_size_lpm`, `location`, `duration_sec`, `pump_mode`, `notes`
- `work_orders`: `id`, `leak_id`, `location_node`, `severity_lpm`, `priority`, `assigned_crew`, `estimated_repair_hrs`, `scheduled_start`, `status`

---

## MQTT Topics Specification (see `docs/MQTT_SPEC.md` for the full schema)
- `rig/telemetry` -> published by ESP32 at 1 Hz, nested schema per hardware spec v2 section 5.4.
- `rig/cmd` -> `{pump1, pump2, servo_deg}`; firmware rejects partial commands.
- `rig/status` -> retained, with MQTT Last Will for offline detection.

---

## Recent Decisions
- **Decision #001**: MongoDB selected over SQLite/Relational for schema flexibility, document-oriented time-series indexing, and scalable JSON telemetry storage. Reaffirmed 2026-08-09 — an "improvised" hardware spec re-mentioned SQLite in its task list, but nothing in the codebase implements it; MongoDB remains the actual persistence layer throughout.
- **Decision #002**: Flat backend structure (`detectors`, `fusion`, `localization`, `replay`, `scheduler`, `alerts`, `impact`, `reports`) chosen to keep the shared `DetectionPipeline` the single code path for both live and replay data.
