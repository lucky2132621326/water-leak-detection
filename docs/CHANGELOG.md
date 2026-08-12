# CHANGELOG

## [2026-08-11] — Acoustic ML channel, per-mode pressure, fabricated-number sweep

### Firmware unblocked (Priority 1)
- **DLPF was running at 94 Hz, not 260 Hz.** `vibration_sensor.cpp` declared
  `DLPF_260HZ = 0x02`, but on the MPU6050 `DLPF_CFG=2` is 94 Hz — the constant
  was named for the value it should have held. The damage landed exactly on the
  acoustic features: band_mid is 50-150 Hz so everything above 94 Hz was rolled
  off, band_high (150-250 Hz) sat entirely in the stopband and read near-zero
  regardless of leak state, and spectral_tilt was skewed because only its
  numerator was filtered. Now `DLPF_CFG_260HZ = 0x00`, with the full register
  table in the comment.
- `firmware/src/secrets.h` created (gitignored) — `config.h` includes it, so the
  firmware would not compile without it.
- `Wire.setClock(400000)`. A 6-byte accel read drops from ~800 us to ~200 us
  against a 2000 us sample budget: ~10x headroom instead of ~2.5x. Overrun the
  budget and the spin-to-next-instant becomes a no-op, the sample rate silently
  falls, and the whole frequency axis shifts — moving the band edges the
  features are defined against.
- `scikit-learn` pinned to **exactly 1.6.1**, the version that trained the
  bundle. Under 1.9.0 it loaded but sklearn declined to guarantee the
  predictions; a model that loads and quietly mispredicts is worse than one that
  refuses to load.

### Acoustic ML channel (Priority 2)
- `backend/ml/acoustic_features.py` — ONE feature implementation, imported by
  both the training exporter and the runtime detector. Two implementations that
  agree today is how a model ends up scored on inputs it never saw, and the
  failure is silent.
- **Duty-keyed baselines.** P2 cycles demand, so a single EMA baseline chases
  the cycling and the ratio features inherit a phantom swing. Both the
  rule-based and ML acoustic channels now bucket by pump duty, matching the
  bundle's own `{band_*_base: {0.6, 0.8, 1.0}}` structure. `spectral_tilt` is
  immune by construction — same sensor, same instant, two bands.
- `acoustic_ml` detector: predict_proba as confidence, the same persistence
  discipline as every other channel, and UNAVAILABLE (never an exception) on a
  missing bundle, corrupt bundle, sklearn mismatch, absent accelerometer, or
  null piezo / water temperature.
- **Honesty gate.** `enabled` defaults False in code. Live mode refuses any
  bundle whose `note` is not exactly `'trained on physical ground truth'`. The
  shipped bundle reads `'SYNTHETIC — not valid results'`, so it demonstrates the
  integration in mock and is refused in live. The note travels on every result
  and is rendered as a visible banner, not a tooltip.
- `scripts/export_acoustic_training.py` — the retraining path. Rows missing any
  model input are DROPPED, never imputed: filling a gap with a mean teaches the
  model that the mean is what a missing sensor looks like.

### Pressure: mock only, labelled SIMULATED (Priority 3)
- **Live mode has no pressure at all.** Not a field, not a detector, not an
  import — `DetectorManager` constructs `SimulatedPressureDetector` only in mock
  and imports it lazily inside that branch, so a live process never loads the
  module.
- **The critical labelling bug is fixed.** Alerts read "pressure 2.38 bar
  (measured)" and "trending down to 2.04 bar (estimated)". Nothing was measured
  and nothing was estimated — every value was generated. The words "measured"
  and "estimated" no longer appear anywhere near pressure; it is SIMULATED, with
  a visible badge.
- **Physically coherent.** Pressure now follows a pump curve (shut-off head
  0.85 bar — realistic for a 12V diaphragm pump, not the fabricated 2.5 bar) and
  is computed from the same `q_in` and `total_leak` that drive flow and current.
  The three cannot contradict: verified at 418→330 mA, 0.548→0.430 bar,
  band_mid 0.029→0.162 across one leak.

### Fusion handles a variable channel count
- 6 live, 7 mock, renormalised over contributing detectors so effective weights
  always sum to 1.0.
- **The corroboration rule now counts SENSOR GROUPS, not detectors.**
  mass_balance/cusum/mnf are one flow measurement; acoustic/acoustic_ml share
  one accelerometer. Counting detectors let a dead outlet meter trip the rule
  with three "agreeing" views of one broken number.
- Weights rebalanced after this change dropped `small_leak` to zero recall and
  made mock and live disagree on the same leak. `tests/test_mode_channels.py`
  now asserts that parity directly.

### Fabricated numbers removed (Priority 4)
- **Per-tier false-positive rates deleted.** Every alert shipped "1% / 3% / 8% /
  20% by confidence tier", citing a DECISIONS.md figure never measured against
  logged leak events. Now `null` plus an explicit basis string explaining how a
  real figure would be obtained.
- **`mnf?.confidence ?? 0.700`** in DetectionEngineView invented a 70% MNF
  confidence whenever MNF had nothing to say — which is most of the day, since
  it only evaluates 01:00-05:00. Every other detector fell back to 0. Now "—".
- Localization no longer claims "pressure drop propagation mapping"; it does a
  Branch A step test.

### Mock fidelity (Priority 5)
- Per-run mounting gain: a hand-fitted accelerometer couples differently every
  time, so absolute band energies are not comparable across runs. Anything that
  accidentally depends on absolute level now fails in mock rather than on the
  bench.
- Cavitation bursts: short, loud, broadband, and with no leak behind them — the
  acoustic channel's main false-positive source. A corpus without them overstates
  precision.

### Known limitations
- The ML channel costs ~15 ms per sample (300-tree forest, per-call overhead;
  100x faster batched). Irrelevant at 1 Hz runtime, but offline scenario scoring
  is now minutes rather than seconds.
- Firmware not compile-verified — PlatformIO is not installed on the dev machine.
- The 1.28 s vibration burst still exceeds the 1000 ms telemetry interval. Flow
  rates self-correct via measured elapsed time; command latency ~1.3 s.
- `resolve_pump_duty`'s definition must match whatever the training notebook
  used to bucket its baseline. That definition is not stored in the bundle and
  cannot be verified from it.

## [2026-08-11] — PR architecture reconciliation

- Retained Mock Data and Live Sensors as the only operating modes and added
  explicit nested/flat ESP32 wire adapters feeding one canonical nested DTO.
- Made the detection pipeline DTO-only and routed online ingestion plus both
  benchmark scorers through the same normalization contract.
- Retained configurable CUSUM recovery, learned/servo localization, the CP-SAT
  scheduler, raw hardware metadata, and asynchronous WhatsApp alerts.
- Made causal/high-confidence localization outrank default zone guesses in the
  incident and work-order summary.
- Disabled WhatsApp for synthetic mock incidents by default.
- Removed unsupported live-pressure/solenoid/air-bubble assumptions while
  retaining the explicitly labelled mock-only simulated-pressure channel. Live
  commands match the ESP32's actual `pump1`/`pump2`/`servo_deg` contract, and
  physical leak windows are logged through Experiment Control.
- Verified 159 Python tests plus 74 subtests, backend self-test, TypeScript,
  production web build, and ESP32 PlatformIO release compilation.

## [2026-08-11] — Plausibility guard, three latching bugs, clock integrity

### Physical plausibility guard (resolves the open `sensor_fault` failure)
`backend/detectors/plausibility.py`. The open design question was how to stop an
outlet-meter dropout being reported as a burst pipe. The answer taken is to veto
on **contradiction**, not on missing corroboration.

- **Why a corroboration rule was rejected.** "Require the current sensor to
  agree" would destroy small-leak sensitivity: 0.30 L/min predicts a ~10 mA
  drop, under the detector's 25 mA threshold, so that channel is *correct* to
  stay quiet. Vetoing on silence suppresses the leaks the system exists to find.
- **What it does instead.** It predicts what each independent channel *should*
  read if the flow claim were true: a current shift proportional to residual,
  plus an acoustic response above the configured floor. A channel may veto only when the
  predicted effect clears its own threshold by `margin` (2.0) and it still reads
  baseline. A dropout claims 5.2 L/min, requiring a 183 mA drop; 10 mA was
  observed. That is positive evidence of an instrument fault.
- **Fails open.** Unconfigured, uncalibrated, unavailable or pump-off channels
  cannot veto; any corroborating channel cancels a veto; and a hard
  `min_residual_lpm` floor (0.75) protects small leaks regardless of calibration.
- **Never silent.** Suppression surfaces as `sensor_fault` in the response, an
  amber Instrument Fault banner in Detection Engine, and text in the evidence
  string. A swallowed alarm would be its own dishonesty — a meter has died and
  the operator must learn that.
- Result: **11/11 scenarios pass, with every leak scenario's recall
  bit-identical.** Guard on vs. off differs on exactly one line.

### Three instances of one latching bug
Recovery time scaled with leak duration — a detector alarms correctly, then
stays alarming for a period nobody chose. Already fixed once in mass balance;
the fix had never been carried across.

- **`CUSUMDetector.s_pos` was unbounded.** A 2-minute 2.5 L/min leak drove it to
  286, decaying at ~0.13/sample — **36 minutes latched** after the valve shut.
  Capped at 2×h; recovery is now a constant ~38 samples. Masked until now only
  because fusion needs two methods, so one stuck detector could not alarm alone.
- **`MNFDetector.consecutive_triggers` was unbounded.** A 160-second night leak
  kept MNF latched **156 seconds** past recovery. Capped, exactly as mass
  balance was.
- `tests/test_detector_recovery.py` asserts the invariant that kills the class:
  **recovery time must not depend on leak duration.**

### Localization sent crews to the wrong pipe
`servo_state_deg` (a deliberate isolation test) was checked *after*
`q_branch_lpm > 0.3` (a weak hint), so a **Branch B leak was reported as Branch
A with HIGH confidence** whenever the branch carried any flow.
- Isolation evidence now wins outright.
- Branch flow alone is reported **LOW**, not HIGH: the branch meter sits at the
  branch *inlet* and reads the same whether or not the leak is downstream of it.
  It says a branch is in use, not that it is leaking.
- Results now carry a `basis` string explaining which signal was used.

### Clock integrity
- **The rig publishes uptime as a timestamp.** `firmware/src/main.cpp` falls
  back to `millis()/1000` until NTP syncs, putting a different epoch in the same
  field. Every stored sample, alert start time and latency figure is then
  computed against a bogus origin — and ~20 hours of uptime maps *into* the
  01:00–05:00 window, switching MNF on for a rig that is not at night.
  `repair_timestamp` substitutes server receive time and counts it
  (`clock_substituted_count`); the sample's flow data is good, so it is repaired
  rather than dropped.
- **Mock scenarios were anchored to `now`**, so running the suite between 01:00
  and 05:00 silently activated MNF for scenarios never meant to reach it.
  Scenarios without a declared `start_time` now anchor to midday, deterministically.

### Harness holes closed
- **`night_flow` never exercised MNF.** The scorer pinned `base_ts=0.0`, which
  resolves to 05:30 local — just outside the window. The scenario met its recall
  target on the other detectors, so nothing looked wrong. With MNF genuinely
  participating, its recall rose **0.67 → 0.92**.
- **`ConfidenceEngine`'s CRITICAL escalation was dead code.** No caller ever
  passed `persistence_sec`, so `active_methods_count >= 3 and persistence_sec
  >= 10` could never evaluate true. The pipeline now passes real elapsed time.
- **Scenario pass rate is now a test.** `backend/benchmark/scenario_scorer.py`
  scores a scenario without MongoDB, and `tests/test_scenarios.py` enforces all
  10 graded scenarios. The rate previously lived in a handoff note; a number in
  a document does not fail a build.

Tests: **96 → 141 passing.** New: `test_plausibility.py`, `test_scenarios.py`,
`test_detector_recovery.py`, `test_localization.py`, `test_clock_integrity.py`.

## [2026-08-10] — Interactive Mock Data Mode

Mock Data Mode was still an auto-looping fixed script — closer to the old Replay
Mode than intended. It is now a controllable bench.

### Interactive leak control
- **`backend/mock/leak_control.py`** — mutable leak state (on/off, rate, branch,
  ramp) read by the generator on *every* sample, so changes take effect on the
  next telemetry tick.
- `/api/leak/toggle` now works in **both** modes: it publishes to `rig/cmd` in
  Live Sensor Mode and mutates the generator in Mock Data Mode. The previous
  version refused leak commands in mock, reasoning that mock leaks belong in the
  scenario — that imported a hardware constraint into software that has none.
- New **Manual Control (free run)** scenario: healthy baseline, no scripted
  leaks, real advancing wall-clock timestamps.
- New `LeakBenchControls` component (branch selector, rate slider + presets,
  ramp control) shown in Live Monitoring for both modes.
- Custom scenario builder in Mock Scenarios — the backend already accepted an
  arbitrary ScenarioSpec; this is a form over it, not a second code path.

### Generator physics corrected
- **Residual did not equal the injected leak.** `q_out` added branch flow back
  in, double-counting it: a clean baseline read −0.377 L/min instead of ~0.02.
  Now `q_out = q_in − branch_flow − total_leak − bias`, so
  `residual = q_in − q_out − q_branch` is exactly the injected leak.
- **Branch leaks localized to Main_Trunk.** LocalizationService keys on
  `servo_deg`, which the mock never emitted. The generator now emits it
  (45 = Branch A, 90 = Branch B) and the DTO parses it from flat payloads, so a
  branch leak localizes correctly without touching detection logic.

### Replay removed from the operating app
- `/api/replay/*` → `/api/benchmark/*`.
- Dashboard "Replay Run" → "Mock Data"/"Live Sensors"; "Injected Leak" → live
  "Current Leak".
- `SystemStatusRow` still tested `mode === "replay"`, which could never match
  after the rename — the ESP32 card would have read "Offline" in mock mode.
- Deleted the stale `RUN_001` seed data (300 telemetry, 3000 detections) that
  was surfacing as the current detection session, plus `seed_runs.py` and the
  dead `roc_generator`/`latency_analysis`/`calibration_analysis` modules.
- `BenchmarkScorer` retained — offline scoring is an analysis tool, not a mode.

### Data separation
- `AlertService.savings()` and `counts()` take `include_mock` (default False for
  savings). Three new tests cover the exclusion rule.

## [2026-08-10] — Two operating modes: Mock Data & Live Sensor

Replay is no longer an operating mode. The system now has exactly two, and they
differ only in where telemetry originates. See `docs/OPERATING_MODES.md`.

### Single shared ingestion path
- **`backend/ingestion/`** — `TelemetrySource` (ABC) + one `TelemetryIngestor`.
  Replaces the near-duplicate `LiveTelemetryIngestor.handle_payload` and
  `ReplayPlayer._play`, which had drifted apart in eight ways: replay skipped
  validation entirely, bypassed the typed DTO, persisted neither telemetry nor
  detections, hardcoded `pressure_source="logged"` (making the pressure detector
  untestable without hardware), and computed `leak_active` from detector output
  while live used solenoid ground truth.
- `_flatten_telemetry`'s two branches collapsed to one. `leak_active` now always
  means ground truth, so the dashboard can honestly show "detector says X while
  the valve is actually Y".
- **Detector state is reset on every mode switch** — otherwise a mock scenario
  would inherit the rig's learned baselines.

### Mock Data Mode
- **`backend/mock/`** — declarative, seeded scenarios emitting the exact ESP32
  wire format, so mock data enters through the same validator and DTO as live.
- Ten built-ins covering no-leak, small, large, sudden, gradual, branch-specific,
  night-flow (clock-controlled, the only way to exercise MNF), sensor noise,
  sensor faults, and multiple simultaneous conditions.
- Models motor-current and pressure coupling, so both those detectors are
  testable without hardware.
- Two paths: **stream** into the dashboard, or **score** instantly against
  ground truth.

### Detector bugs found by the new scenarios
Both were pre-existing and masked; the mock harness surfaced them.
- **Mass balance absorbed its own leak.** The rolling baseline included leak
  samples, so a 0.3 L/min leak tripped at t=122 then went silent by t=130 as the
  threshold climbed from 0.21 to 0.57 against an unchanged residual. Recall on
  `small_leak` was **0.00**; it is now 0.67 at 100% precision. Only quiet samples
  update the baseline now.
- **Recovery time scaled with leak duration.** `consecutive_triggers` was
  unbounded and decremented one-per-sample, so a 2-minute leak kept the detector
  latched for 2 minutes after the valve shut. Every false positive on
  `small_leak` sat *after* the leak had closed. Now capped at the persistence
  count.

### Renames and removals
- `ReplayRunner` → **`BenchmarkScorer`** (`backend/benchmark/`). It scores stored
  runs offline and powers Analytics/Reports — an analysis tool, not a mode.
- Deleted `backend/mqtt/` (superseded by `backend/ingestion/mqtt_source.py`),
  `ReplayPlayer`, and `ReplaySystemView`.
- Frontend: **Mock Scenarios** tab replaces Replay & Benchmark; header badge
  reads MOCK DATA / LIVE SENSORS.

### Data separation
- Telemetry, detections, alerts and runs carry `source: "mock" | "live"`.
- Mock records are excluded from operational KPIs by default
  (`/api/savings?include_mock=true` to include). Analytics and Reports use the
  full corpus deliberately — scenarios with known ground truth are what a
  benchmark needs.

### Known finding
`sensor_fault` fails: a flow-meter dropout is indistinguishable from a total
leak using flow alone, and mass balance and CUSUM both consume the same residual
so two "agreeing" detectors trip fusion. Left visible rather than silenced.


## [2026-08-10] — Honesty pass, sensor fusion, real solvers

A full audit found the dashboard was roughly half live data and half leftover
mockup, with several panels stating things that were not merely stale but
false. Everything below is now computed or observed.

### Removed fabricated data
- **Analytics was entirely invented** and contradicted the system's own Replay
  screen — it claimed 96.4% precision / 2.1 s latency against real measured
  values of 100% / 13.0 s, and "12 benchmark runs" when one existed. Replaced
  with `backend/analytics/benchmark_analytics.py`, which recomputes precision,
  recall, F1, latency, a swept ROC curve and per-detector comparison by
  replaying stored runs through the production pipeline. Shows an empty state
  when no runs exist rather than placeholder numbers.
- **Dashboard status row** reported "MQTT Broker: Connected" with no broker
  running. Replaced with `/api/status`, which observes each component and
  reports faults.
- **Detector Status** was hardcoded and *inverted* — it headlined Mass Balance
  as the strongest alarm while that detector was not firing at all. Now reads
  live per-detector state.
- **Active Experiment** and **Recent Alerts** showed May 2025 dates on an
  Aug 2026 system. Both now derive from real runs and incidents.
- Deleted the dead `simulation/` package (`wntr_model.py` imported no WNTR and
  called `np.sin` without importing numpy — it would raise `NameError` if ever
  executed; nothing imported it), the unmounted `WNTRSimulationView`,
  `HomeView`, `PhaseSelector`, and the decorative `/api/simulation/wntr` route.
- Removed fabricated fallback values across the UI. A dead backend previously
  rendered `12.45 / 11.08 / 1.42 A` and looked like a live rig; views now read
  zero and the status row reports the fault.

### Corrected wrong facts
- Calibration listed **GPIO 18/19/21** for the flow meters; the firmware uses
  **34/35/32** — and GPIO 21 is the INA219 I²C data line, so anyone wiring from
  that screen would have shorted a flow meter onto the power-sensor bus.
- Calibration K-factors (445.2/451.8/447.1) did not match the flashed firmware
  (456/448/452).
- The fusion formula printed `0.20` for Current and MNF while the engine used
  `0.25` and `0.15`. Weights now come from `thresholds.yaml` via
  `/api/detectors/config`, so the published formula is the running one.
- Localization advised *"**Actuate** solenoid valve…"*, contradicting the
  project's own no-control-instructions guardrail. Reworded as diagnostic
  guidance.
- The telemetry chart was labelled "Last 10 Minutes" while rendering 12 samples
  (~12 s) and discarding 90% of the data the API already served. Now renders the
  full 120-sample window with a label derived from the data.

### Made dead controls work
- Leak injection, pump and air-bubble controls now publish real commands to
  `rig/cmd` in live mode, and are **refused** in replay mode rather than
  returning success and doing nothing.
- **Ground-truth logging is real.** `ExperimentService` was in-memory only with
  no route; it now persists runs and leak events to MongoDB, and stamps
  `run_id` onto live telemetry while a run is active — which is what makes a
  live rig session scoreable.
- Calibration and self-test buttons now hit `/api/calibration` and
  `/api/self-test`; the latter runs the real `system_self_test.py`.

### Acoustic channel and honest pressure handling
- The fifth channel is the MPU6050/piezo acoustic signature, not a pressure
  transducer. Missing acoustic hardware reports inactive and its fusion weight
  is redistributed across contributing detectors.
- The rig has no physical pressure sensor. Any derived pressure is labelled
  estimated and is never scored as independent evidence, avoiding fabricated
  agreement with the mass-balance signal.

### Real CP-SAT scheduling
- `cp_sat_scheduler.py` was `crews[idx % len(crews)]` with a hardcoded start
  time while calling itself a CP-SAT scheduler. It now builds a genuine
  constraint model (no-overlap per crew, skill eligibility, travel penalty)
  and minimises severity-weighted completion time, falling back to a
  severity-ordered greedy assignment that **labels itself as such** if the
  model is infeasible. Adds `ortools` to requirements.

### Config
- `settings.yaml` carried `database:` and `detector:` blocks that nothing read
  and that contradicted the values actually in force (persistence 10 vs 5,
  cusum h 3.0 vs 5.0). Removed, so there is one source of truth per concern.

### Tests
- 93 passing (was 66). New: `test_pressure_detector.py` (15) and
  `test_scheduler.py` (12), including regression cover for the two subtle bugs
  found while building them — a pressure baseline that drifted into a sustained
  leak, and a CP-SAT interval whose fixed size made the model infeasible.


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
