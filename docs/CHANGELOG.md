# CHANGELOG

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
