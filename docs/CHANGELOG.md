# CHANGELOG

## [2026-08-09] (cont'd) — Acoustic channel end-to-end + localization/docs honesty pass

### Added
- Fifth detection channel, acoustic (MPU6050 + piezo): `backend/detectors/acoustic_detector.py`
  (ratio-to-baseline, not raw threshold), wired through `DetectorManager`,
  `FusionEngine` (reweighted 32/20/16/12/20% + independent-agreement bonus
  when acoustic corroborates a flow/current channel), `DetectionPipeline`,
  `TelemetryDTO`, `TelemetryRepository`, both replay paths, and
  `DetectionEngineView.tsx` (new card + vibration spectrum panel, honest
  "no sensor data" empty state).
- Temperature compensation (DS18B20): `CalibrationRepository.temp_k_coeff`
  (default 0.0, no-op until characterised), applied in `pipeline.py`.
- Firmware drivers for all three new v2 sensors: `vibration_sensor.{h,cpp}`,
  `piezo_sensor.{h,cpp}`, `temp_sensor.{h,cpp}`, wired into `main.cpp` on a
  5s cadence (both bursts are blocking, too slow for the 1Hz loop) and
  `mqtt_client.cpp`'s telemetry payload. **Not compiled/flashed** — no
  PlatformIO toolchain available; needs real hardware verification.
- Calibration UI + API: `vib_baseline_band_mid`, `temp_k_coeff` fields,
  verified via live save/readback.

### Fixed
- `LocalizationService` no longer claims "Branch_A, HIGH confidence" from
  servo state alone — it now uses `BranchAnalyzer.evaluate_isolation()` to
  compare residual before/after closing the servo, waiting for the reading
  to settle first. Caught and fixed a real bug in the same pass: a fully
  successful isolation (residual near zero) was hitting the generic
  "no leak" bailout before the isolation-test check ran, silently losing
  the confirmation.
- `Branch_C` removed from `known_zones` — the rig has no sensor that can
  distinguish leak tee C from A/B/the main line; listing it as a possible
  output overclaimed precision the hardware doesn't support.
- `docs/PROJECT_CONTEXT.md`: replaced a fabricated "ONLINE"/"WORKING"
  hardware status table (fixed IP, wrong GPIO pins, never bench-verified)
  with an honest one; removed a fictional 5-person team roster; removed
  false "completed" claims for WNTR/CP-SAT (both decorative/renamed);
  corrected the MongoDB collection schema description to match reality.

See also the same-day entry above for CORS/CP-SAT-rename/FP-rate-honesty/
schema.sql-deletion fixes from earlier in this session.

## [2026-08-09] — Audit fixes + hardware spec v2 (acoustic channel)

### Changed
- Hardware spec updated to v2 (`docs/HARDWARE_INTEGRATION_SPEC.md`): three
  new sensors (MPU6050, piezo, DS18B20) add a fifth detection channel
  (acoustic) and two new GPIO assignments (piezo GPIO33, DS18B20 GPIO4). No
  status LED. `tools/mock_publisher.py` now emits `vibration`/`temp` fields;
  firmware/backend/UI changes for the new channel are pending confirmation.
- CORS restricted from wildcard (`allow_origins=["*"]`) to an explicit
  allowlist (`backend/api_server.py`, `CORS_ALLOWED_ORIGINS` env var) — the
  API has unauthenticated mutating routes (mode switch, work-order dispatch,
  ground-truth logging), so wildcard CORS let any origin script the rig.
- `backend/scheduler/cp_sat_scheduler.py` renamed to `work_order_scheduler.py`
  (`WorkOrderScheduler`) — it was plain round-robin (`idx % crew_count`),
  never actual OR-Tools/CP-SAT constraint solving. Also fixed a hardcoded
  `"2026-08-03 10:30:00"` dispatch timestamp to use real current time.
- False-positive rate table (`backend/response/response_builder.py`) is now
  explicitly labeled illustrative/not-measured (`rate_is_measured: false` in
  the API response, matching UI copy) — it's an asserted per-tier estimate,
  not computed from a labeled validation set.
- `/api/simulation/wntr` response now carries an explicit `is_simulated: true`
  flag — it's a hardcoded sine-wave curve, not a real WNTR/EPANET solve.
  (`WNTRSimulationView` was already unreachable from the dashboard nav.)

### Removed
- `backend/storage/schema.sql` — stale, unused SQLite artifact; nothing in
  the codebase has read or executed it since MongoDB was adopted
  (docs/DECISIONS.md #001). If you're looking for it, persistence is Mongo.

## [2026-08-05] — Impact, Alert Center & Automatic Reports

### Added
- **Impact engine** (`backend/impact/`): converts a detector's estimated leak
  rate into the terms operators decide in. `water_loss.py` (L/min → hour / day /
  week / month / year + relatable equivalents), `cost_estimator.py` (volumetric
  tariff applied per kilolitre), `severity.py` (MINOR/MODERATE/MAJOR/CRITICAL
  bands + repair-urgency recommendation), `progression.py` ("what if nobody
  fixes this?" projection), composed by `impact_service.py`. Tariff, bands and
  equivalents live in the new `backend/config/impact.yaml` so a utility can
  retune them without a code change.
- **Alert Center** (`backend/alerts/alert_service.py`): aggregates per-sample
  detection responses into durable leak *incidents* with a lifecycle
  (ACTIVE → RESOLVED / FALSE_POSITIVE), persisted to a new `alerts` collection.
  Consecutive alarm samples merge into one incident; re-ingesting a timestamp an
  incident already covers updates it rather than duplicating, which is what
  keeps the looping replay player from producing hundreds of alerts per run.
  `is_open` (detector still in alarm) is tracked separately from `status`
  (operator disposition).
- **Water Savings counter**: repaired incidents credit the water they would
  have lost over a configurable 30-day horizon at their peak observed rate.
  Dismissed false positives are never credited, and reopening reverses the
  credit.
- **Leak History Explorer**: server-side filtering by status, zone, severity,
  likelihood, date range and free text, plus a monthly incident trend.
- **Automatic experiment reports** (`backend/reports/`): one call turns a stored
  run into a full write-up — metadata, ground-truth leak events, detector
  metrics scored by the real `ReplayRunner`, inline-SVG telemetry graphs with
  leak windows shaded, quantified impact, and auto-generated conclusions.
  Rendered as standalone printable HTML (`/api/reports/experiment/:id/html`)
  rather than via a PDF library, so the browser's Save-as-PDF is the export path
  and the artifact stays dependency-free.
- New API routes: `/api/impact/{config,current,simulate}`, `/api/alerts`,
  `/api/alerts/summary`, `/api/alerts/:id/{resolve,false-positive,reopen}`,
  `/api/savings`, `/api/reports/experiment/:run_id[/html]` — all proxied through
  `server.ts` (which now also forwards query strings and passes non-JSON
  responses through verbatim).
- Frontend: `ImpactSimulatorView` (interactive what-if simulator),
  rewritten `AlertsView` (incident queue with disposition actions), new
  `LeakHistoryView`, rewritten `ReportsView`, and an `ImpactSummaryStrip` on the
  Dashboard. `ViewErrorBoundary` now contains a render failure to the current
  view instead of blanking the whole app.
- Tests: `tests/test_impact.py` (19) and `tests/test_alert_service.py` (20),
  the latter fully isolated from MongoDB via `enable_persistence=False`.

### Fixed
- `WorkOrderRepository.list_all()` returned Mongo `_id` (an `ObjectId`), which
  is not JSON-serializable and would break `/api/work-orders` once any work
  order existed. Now projected out, as is the `_id` Mongo stamps onto the dict
  during dispatch.
- `AlertsView` and `ReportsView` were entirely hardcoded mock data with no
  backend calls; both now read real state.
- The Alerts badge in the sidebar/header was a hardcoded `3`; it now reflects
  the real active-incident count.

### Notes
- Impact figures are indicative projections, and the progression simulator
  assumes a constant leak rate (stated in its own `assumptions` field) — real
  leaks worsen, so the projection is a conservative lower bound.
- The repair-urgency recommendation is deliberately *scheduling* advice only;
  `tests/test_impact.py` asserts no valve/pump control language can appear in it.

## [2026-08-05]
### Fixed
- Firmware (`firmware/src/`) was Serial-print scaffolding with no real WiFi/MQTT
  stack, fake INA219 readings, and no interrupt-driven flow counting — rewritten
  with real `WiFi.h`/`PubSubClient`/`ArduinoJson`, `attachInterruptArg`-based
  pulse counting (also fixed a missing `*60` unit bug), real I2C INA219 reads,
  `rig/cmd` command handling, and `ESP32Servo` PWM output. Added the
  previously-missing `firmware/platformio.ini`. Fixed `README.md`'s GPIO table,
  which contradicted the firmware and `HARDWARE_SETUP.md`.
- `backend/`'s "MongoDB persistence" was entirely stubbed (`save_sample()`
  built a dict and returned it without writing anywhere). Added a real
  `backend/repositories/db.py` + rewritten repositories that actually persist
  telemetry/detections/leak_events/work_orders/events.
- MNF (night-flow) detection — required by the problem statement — had zero
  implementation. Added `backend/detectors/mnf_detector.py`.
- Deleted dead, unimported duplicate files (`backend/detectors/fusion.py`,
  `current_signature.py`, `cusum.py`, `backend/localization/localizer.py`,
  `backend/replay/replay.py`) and wired the previously-unused 3-sigma
  `mass_balance.py` into `detector_manager.py` (also fixed a `numpy.bool_`
  JSON-serialization bug in it).
- `server.ts` reimplemented detection from scratch over `Math.random()`
  telemetry, fully disconnected from the Python backend. Replaced with a thin
  proxy to a new `backend/api_server.py` (FastAPI), which owns real
  live/replay pipeline state.

### Added
- `backend/pipeline.py`: shared `DetectionPipeline` used by both live MQTT
  ingestion (`backend/mqtt/subscriber.py`) and replay
  (`backend/replay/replay_runner.py`) — same detectors/fusion/localization
  either way.
- `backend/response/response_builder.py`: shapes pipeline output into
  likelihood score, time window, evidence text, false-positive disclaimer,
  and work-order summary (per the problem statement's output requirements).
- `backend/llm/summary_client.py`: Azure OpenAI work-order summaries with a
  deterministic template fallback.
- `backend/utils/pressure_estimate.py`: derives an estimated `pressure_bar`
  from flow/pump state, since no physical pressure sensor exists on the rig.
- `backend/replay/seed_runs.py`: seeds a real replay run (`RUN_001`) with
  genuine stored telemetry + ground-truth leak events, replacing the
  hand-authored placeholder JSONs in `experiments/leaks/`.
- Live/Replay mode toggle in the dashboard header, backed by `/api/mode`.
- Mounted the previously-unreachable `ReplaySystemView` as a sidebar tab and
  wired it to evaluate by `run_id` against real stored data (was ignoring the
  run selector and only reacting to a sigma slider via a fake formula).

## [2026-08-03]
### Added
- Completed initial AI-Agent friendly repository structure.
- Created `PROJECT_CONTEXT.md` with strict AI AGENT INSTRUCTIONS.
- Implemented Phase 1 MQTT Telemetry collector and MongoDB database collections.

- Added Phase 2 Mass Balance detector and Replay system.
- Added Phase 3 Multi-Method Detection Engine (`current_signature_detector.py`, `cusum_detector.py`, `detector_manager.py`).
- Integrated Fusion Engine (`fusion_engine.py`) and Explainable Confidence Engine (`confidence_engine.py`).
- Added Branch Localization Service (`localization_service.py`, `branch_analyzer.py`) with servo-based active branch isolation.
- Created Research-Grade Evaluation Analytics (`roc_generator.py`, `latency_analysis.py`, `calibration_analysis.py`).
- Added Phase 3 documentation: `DETECTOR_DESIGN.md`, `LOCALIZATION.md`, `ANALYTICS.md`.
- Added Phase 4 WNTR EPANET hydraulic simulator and CP-SAT Work Order Scheduler.
- Built interactive Web Workbench & Dashboard.
