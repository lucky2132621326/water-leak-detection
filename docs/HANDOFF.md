# Session Handoff

Everything done in this working session, why, and what is still open. Written so
a fresh session can pick up without re-deriving context.

**Project:** Water Distribution Leakage Detection (Pressure/Flow Anomalies)
**Stack:** ESP32 firmware → MQTT → Python/FastAPI → MongoDB (Docker) → React dashboard

---

## 1. How to run it

MongoDB runs in Docker; the app is two processes.

```bash
docker compose up -d --wait                 # MongoDB (container wld-mongo, port 27017)
source .venv/bin/activate                   # required — see §7
python -m uvicorn backend.api_server:app --host 127.0.0.1 --port 8000   # terminal 1
npm run dev                                 # terminal 2 → http://localhost:3000
```

Boots into **Mock Data Mode** with the `manual_control` scenario. No hardware or
MQTT broker needed. Optional broker for Live mode:
`docker compose --profile live up -d`.

Verify: `python -m unittest discover -s tests -p "test_*.py"` (96 tests) and
`npx tsc --noEmit`.

---

## 2. Architecture as it stands

**Two operating modes**, differing only in where telemetry originates:

```
MockTelemetrySource ──┐
                      ├─→ TelemetryIngestor ─→ validate → DTO → DetectionPipeline
MqttTelemetrySource ──┘      (ONE class)        → fusion → confidence
                                                → localization → alerts
                                                → impact → dashboard
```

Everything right of `ingestor.ingest(raw)` is one code path. The mock generator
emits the **exact ESP32 wire format**, so mock data passes through the same
validator and DTO as live data — divergence is structurally impossible rather
than a convention.

Full detail: `docs/OPERATING_MODES.md`.

### Key modules added this session
| Path | Purpose |
|---|---|
| `backend/ingestion/` | `TelemetrySource` ABC, the single `TelemetryIngestor`, `MqttTelemetrySource` |
| `backend/mock/` | `scenarios.py` (11 declarative scenarios), `generator.py`, `mock_source.py`, `leak_control.py` |
| `backend/impact/` | water loss, cost, severity, progression |
| `backend/alerts/alert_service.py` | incident lifecycle + savings KPI |
| `backend/analytics/benchmark_analytics.py` | computed metrics/ROC (replaced hardcoded modules) |
| `backend/benchmark/` | `BenchmarkScorer` (was `ReplayRunner`) — offline scoring only |
| `backend/reports/` | printable experiment reports (inline SVG, no PDF lib) |
| `backend/detectors/pressure_drop_detector.py` | 5th detector |
| `firmware/src/pressure_sensor.{h,cpp}` | analog transducer, GPIO 36 |

### Deleted
`backend/mqtt/`, `backend/replay/`, `simulation/`, `ReplayPlayer`,
`ReplaySystemView`, `WNTRSimulationView`, `HomeView`, `PhaseSelector`,
`roc_generator`/`latency_analysis`/`calibration_analysis`, `seed_runs.py`,
and the stale `RUN_001` seed data.

---

## 3. Work completed, in order

### A. Feature build (impact, alerts, reports)
Impact engine (L/min → litres/cost/severity/urgency/progression), Alert Center
with ACTIVE→RESOLVED/FALSE_POSITIVE lifecycle, water-savings KPI, Leak History
explorer, automatic experiment reports. New frontend views: Impact Simulator,
Alert Center, Leak History, Reports. `ViewErrorBoundary` added so one bad view
cannot blank the app.

### B. Docker MongoDB migration
Homebrew MongoDB replaced with `docker-compose.yml` (mongo:7.0 + optional
mosquitto behind a `live` profile). Published on the standard 27017 so
`backend/repositories/db.py`'s existing default works unchanged — **no app
config changes required**.

### C. Honesty pass (large)
An audit found the dashboard was roughly half live data, half leftover mockup,
with several panels stating things that were **false**:
- Analytics was entirely invented and contradicted the app's own measurements
  (claimed 96.4% precision / 2.1 s latency vs. real 100% / 13.0 s).
- Status row said "MQTT Broker: Connected" with no broker running.
- Detector Status was hardcoded and *inverted* — headlined the one detector not
  firing.
- Calibration listed GPIO 18/19/21; firmware uses 34/35/32, and GPIO 21 is the
  I²C data line.
- Fusion formula printed weights that did not match the engine.
- Localization said "**Actuate** solenoid valve", violating the project's own
  no-control-instructions guardrail.
- Dashboard fabricated telemetry (`12.45 / 11.08 / 1.42 A`) when the backend was
  down, so a dead backend looked like a live rig.

All replaced with computed/observed values. Real CP-SAT scheduling (OR-Tools)
replaced a fake round-robin. Config reconciled: `settings.yaml` had `database:`
and `detector:` blocks nothing read that contradicted the live values.

### D. Pressure sensor, end to end
Firmware driver on GPIO 36 (ADC1 — survives WiFi), oversampled + EMA smoothed,
**omits `pressure_bar` entirely on sensor fault** rather than publishing `0.0`
(which would look like a pressure collapse). New `PressureDropDetector` scores
**only measured** pressure — never estimated, which would double-count the flow
signal. Fusion **renormalises weights over contributing detectors**, so a rig
without a transducer scores on the identical 0–1 scale as before.

### E. Two modes replacing Replay
Replay removed as an operating mode. `ReplayRunner` → `BenchmarkScorer` (kept —
offline scoring powers Analytics/Reports). Mock scenarios with known ground
truth are now the benchmark corpus.

### F. Interactive Mock Data Mode
Mock was still an auto-looping script. Now a controllable bench:
`MockLeakControl` is read on **every** generated sample, so start/stop, branch,
rate and ramp changes land in the next telemetry tick. `/api/leak/toggle` works
in **both** modes — publishes to `rig/cmd` in Live, mutates the generator in
Mock. New `LeakBenchControls` component + custom scenario builder.

---

## 4. Bugs found and fixed (worth knowing about)

| Bug | Impact |
|---|---|
| **Live ingestion was completely broken** | Validator required a `seq` the firmware never sends → 100% of real telemetry rejected. Worse, `from_dict` read nested keys from a flat payload, so a 1.25 L/min leak parsed as residual **0.0** — silently, no error |
| **Mass balance absorbed its own leak** | Rolling baseline included leak samples; threshold climbed 0.21→0.57 while residual held at 0.30. `small_leak` recall was **0.00**, now 0.67 at 100% precision |
| **Recovery scaled with leak duration** | `consecutive_triggers` unbounded, decremented 1/sample → a 2-min leak stayed latched 2 min after closing. Now capped |
| **Two MongoDBs on port 27017** | Local `mongod` on IPv4 + Docker on IPv6 wildcard. No port conflict reported; app silently used the local one while the container sat empty |
| **Generator residual ≠ injected leak** | `q_out` added branch flow back, double-counting: clean baseline read −0.377 instead of ~0.02 |
| **Branch leaks localized to Main_Trunk** | `LocalizationService` keys on `servo_deg`, which mock never emitted. Generator now emits it (45=A, 90=B) |
| **`WorkOrderRepository.list_all()` returned ObjectId** | `/api/work-orders` would 500 once any work order existed |
| **`SystemStatusRow` tested `mode === "replay"`** | Could never match after rename → ESP32 card read "Offline" in mock mode |
| **CP-SAT model infeasible** | Interval size fixed at `duration + max_travel` contradicted the end constraint |
| **`scripts/init_db.py` hardcoded DB name** | Would index a different database than the app uses if `MONGO_DB_NAME` were set |

---

## 5. Current state

- **141 Python tests pass**, `tsc` clean, production build succeeds, self-test
  passes all 6 modules, all 14 dashboard tabs render with zero console errors.
- **11/11 mock scenarios pass** — and the pass rate is now enforced by
  `tests/test_scenarios.py` rather than recorded here. A number in a document
  does not fail a build.
- Verified end-to-end through the UI: normal → Start Leak (Branch A, 1.25 L/min)
  → detected by 4 detectors, `zone=Branch_A`, CRITICAL, ₹13,402/yr → Stop Leak →
  recovered.

### Test files
`test_impact.py` (19), `test_alert_service.py` (23), `test_telemetry_ingestion.py`
(22), `test_pressure_detector.py` (15), `test_scheduler.py` (12),
`test_scenarios.py` (4, covering all 10 graded scenarios via subtests),
`test_plausibility.py` (15), `test_detector_recovery.py` (8),
`test_clock_integrity.py` (10), `test_localization.py` (6),
`test_mass_balance.py` (2). Plus standalone hardware scripts (`test_flow1.py`
etc.) that are demonstration scripts, not regression tests.

---

## 6. Open items

**1. ~~`sensor_fault` scenario fails~~ — RESOLVED 2026-08-11.** The design
decision was taken: a physical plausibility guard
(`backend/detectors/plausibility.py`) that vetoes on **contradiction**, not on
missing corroboration. See `docs/CHANGELOG.md`. 11/11 scenarios now pass with
every leak scenario's recall bit-identical.

**1a. Calibrate the guard's two constants against the real rig.** They currently
hold the mock's physics (`35.0` mA and `0.35` bar per L/min). Measure them: open
a known leak, record how far pump current and line pressure actually move. Wrong
values do not cause false alarms — they cost sensitivity to instrument faults —
and setting either to `0` disables that channel's veto. In
`backend/config/thresholds.yaml` under `plausibility:`.

**1b. `min_residual_lpm` (0.75) has not been tuned.** It is a hard floor below
which the guard never vetoes, protecting small leaks from a mis-set constant.
It also means an instrument fault producing a *small* implausible residual will
not be caught. That trade is deliberate — missing a small leak is worse — but
the number itself is a judgement call, not a measurement.

**1c. Firmware publishes uptime as `ts` before NTP syncs.**
`firmware/src/main.cpp:77` falls back to `millis()/1000`, a different epoch in
the same field. The backend now detects and repairs this (`repair_timestamp`,
counted as `clock_substituted_count`), but the cleaner fix is firmware-side:
publish an explicit `clock_synced` flag, or withhold telemetry until NTP
completes. Watch that counter on first bring-up — a non-zero value means the rig
never got its clock.

**2. Pressure sensor untested against real hardware.** Validated against the
payload the firmware constructs, not a physical transducer. When wiring, confirm
`PRESSURE_DIVIDER_RATIO` matches the fitted resistors (1.5 for 10k/20k) — if
wrong, every reading is proportionally wrong. See `firmware/docs/PINOUT.md`.

**3. Live Sensor Mode untested against a real rig.** No ESP32 or broker
available here. On first bring-up watch the backend log for
`[Ingestor:live] rejected telemetry:` — silence means packets are landing.

**4. Firmware still does not publish `servo_deg`.** The mock does; the DTO parses
it optionally. Adding it firmware-side would improve live localization.

**5. `solenoid_state` ground truth is captured but live runs need grouping** to
be scoreable — `ExperimentService` start/stop-run exists and stamps `run_id`,
but the workflow hasn't been exercised on hardware.

**6. Four dashboard panels remain partly cosmetic** — pump/air-bubble controls
are live-only (generator doesn't model them) and say so when refused.

---

## 7. Environment gotchas

- **Activate the venv.** macOS ships `python3` only; bare `python` fails without
  it. PEP 668 also blocks `pip install` outside a venv.
- **Run from the repo root.** `config_loader.py` resolves `backend/config/*.yaml`
  by relative path and silently falls back to defaults otherwise.
- **Only one MongoDB on 27017.** `lsof -i :27017 -sTCP:LISTEN -P -n` — more than
  one listener means the silent-shadowing failure in §4.
- **`.env.example` is reference only** — nothing calls `load_dotenv()`; export
  vars into the shell if you need overrides.
- `server.ts` hardcodes `PORT = 3000` and ignores the env var.

---

## 8. Docs map

| File | Contents |
|---|---|
| `docs/OPERATING_MODES.md` | The two modes, scenarios, interactive control, data separation |
| `docs/IMPACT_AND_ALERTS.md` | Impact engine, alert lifecycle, savings, reports |
| `docs/CHANGELOG.md` | Dated entries for every change above, with rationale |
| `docs/TROUBLESHOOTING.md` | Including the dual-MongoDB silent failure |
| `docs/MQTT_SPEC.md` | Wire format — the contract both sources honour |
| `docs/DATABASE_SCHEMA.md` | 7 collections incl. `alerts`, `events`, `source` tags |
| `firmware/docs/PINOUT.md` | Pins + pressure transducer wiring/calibration |
| `README.md` | Setup and run instructions |
