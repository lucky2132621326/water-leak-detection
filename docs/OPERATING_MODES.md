# Operating Modes

The system has exactly **two** modes. They differ in one thing only: where
telemetry comes from.

```
Mock Data Mode
  MockTelemetrySource ──┐
                        │
Live Sensor Mode        ├─→  TelemetryIngestor  ─→ validate → DTO
  ESP32 → MQTT ─────────┘         (ONE class)      → DetectionPipeline
                                                    → fusion → confidence
                                                    → localization → alerts
                                                    → impact → dashboard
```

Everything to the right of `TelemetryIngestor.ingest(raw)` is a single code
path. There is no per-mode branch anywhere in detection, scoring, persistence
or response shaping.

## Why it is built this way

The previous design had a third mode ("Replay") with its own ingestion loop
alongside the live one. Both called the same `DetectionPipeline`, so the
algorithms were shared — but the orchestration around them was duplicated, and
the copies had silently drifted apart in eight ways:

| | Live | Replay |
|---|---|---|
| Validation | `TelemetryValidator` | **skipped** |
| Typed DTO | `TelemetryDTO.from_dict()` | raw dict indexing |
| Saved telemetry | yes | **no** |
| Saved detections | yes | **no** |
| `pressure_source` | `measured` | hardcoded `logged` |
| `leak_active` means | solenoid ground truth | **detector output** |
| `seq` | monotonic counter | from stored doc |
| Alert `source` | `live` | `replay` |

Two of those were serious. Replay bypassed validation entirely, so a malformed
record took a path live would have rejected. And `leak_active` meant opposite
things depending on mode — ground truth in one, the detector's own opinion in
the other.

The `pressure_source` difference had a subtler cost: because the pressure
detector declines to score anything not tagged `measured`, hardcoding `logged`
made the fifth detector **impossible to test without physical hardware**.

Collapsing to one ingestor makes divergence structurally impossible rather than
a thing to remember.

## Mock Data Mode

Generated telemetry with known ground truth, for exercising the whole system
under controlled conditions.

The generator emits the **exact ESP32 wire format** from `docs/MQTT_SPEC.md` —
not a convenient internal structure. That is deliberate: it forces mock data
through the same validator and DTO as live data. A mock sample and a rig sample
are indistinguishable to everything downstream.

### Scenario library

| Scenario | What it tests |
|---|---|
| `manual_control` | Free-run baseline for interactive testing — start/stop leaks yourself |
| `normal_operation` | Control case. Any alarm is a false positive |
| `small_leak` | 0.3 L/min — sensitivity near the detection floor |
| `large_leak` | 2.5 L/min rupture |
| `sudden_leak` | Instant step — detection latency |
| `gradual_leak` | Ramp over 2 min — hostile to thresholds, a CUSUM test |
| `branch_leak` | Localization, not just detection |
| `night_flow` | Runs at 02:00 — the only way to exercise MNF |
| `sensor_noise` | 5× noise, no leak — false-positive test |
| `sensor_fault` | Dropout, spikes, pressure fault — instrument vs. pipe fault |
| `multiple_conditions` | Two overlapping leaks plus noise and a spike |

Scenarios are declarative (`backend/mock/scenarios.py`) and seeded, so a given
scenario produces byte-identical telemetry every run. Regression tests depend
on that. Custom scenarios can be posted to `/api/scenarios/run` without a code
change.

### Physical model

The generator models the two secondary effects detectors depend on, because a
mock rig that omitted them would make those detectors untestable:

- **Motor current** falls as a leak lowers hydraulic resistance
- **Line pressure** sags in proportion to escaping flow

Each meter gets independent noise, so a small residual appears even with no
leak — the same nuisance signal the real rig produces.

### Interactive control

Mock Data Mode is a controllable bench, not a fixed script on repeat. The
**Manual Control (free run)** scenario is a healthy baseline with no scripted
leaks; from **Live Monitoring** you can start a leak, choose its branch and
rate, change it mid-stream, and stop it — each change lands in the very next
generated sample.

`MockLeakControl` holds the operator's intent and is read on every sample. When
an override is in force it *replaces* the scenario's scripted leaks rather than
adding to them, so closing a manually-opened valve cannot silently re-expose a
scripted one. "Release to Scenario" hands control back to the script.

The same bench controls appear in Live Sensor Mode and publish to `rig/cmd`
instead. Identical operator actions, identical downstream pipeline — only the
thing being actuated differs.

### Two execution paths

- **Stream** — one sample/sec (optionally accelerated) into the dashboard, so
  every view animates as it would with a rig attached.
- **Score** — the whole scenario evaluated instantly and graded against its own
  ground truth. A 300-sample scenario completes in milliseconds.

## Live Sensor Mode

`MqttTelemetrySource` subscribes to `rig/telemetry`, decodes JSON, and hands the
payload to the ingestor. It performs no validation, parsing or evaluation of its
own — it is a transport adapter, nothing more.

The bench controls (start/stop leak, branch, rate) are the *same* controls used
in Mock Data Mode — here they publish to `rig/cmd` and actuate the physical
valve instead of mutating a generator. Pump and air-bubble commands remain
live-only, since the generator does not model them; those are refused with an
explanation pointing at the equivalent mock scenario.

## Switching modes

```bash
curl -X POST localhost:8000/api/mode \
  -H 'Content-Type: application/json' \
  -d '{"mode":"mock","scenario_id":"gradual_leak","speed":8}'

curl -X POST localhost:8000/api/mode \
  -H 'Content-Type: application/json' -d '{"mode":"live"}'
```

No application code changes. The dashboard's header badge shows **MOCK DATA** or
**LIVE SENSORS** at all times.

### Detector state is reset on every switch

Every detector is stateful — the mass-balance rolling window, the CUSUM
accumulator, the MNF and pressure baselines. Carrying live-rig state into a mock
scenario (or the reverse) would evaluate the first samples against a baseline
learned under entirely different conditions. `_switch_mode()` builds a fresh
`TelemetryIngestor`, discarding all of it.

## Data separation

| | `source` tag |
|---|---|
| Live telemetry, detections, alerts, runs | `live` |
| Mock telemetry, detections, alerts, runs | `mock` |

Mock records are **excluded from operational KPIs by default**. Letting
synthetic leaks inflate the water-saved figure would make the KPI meaningless —
you would be reporting water saved on leaks that never physically existed.

Pass `?include_mock=true` to `/api/savings` to include them. Analytics and
Reports use the full corpus deliberately: mock scenarios with known ground truth
are exactly what a benchmark needs.

## Benchmark scoring is not a mode

`BenchmarkScorer` (formerly `ReplayRunner`) scores a **stored** run offline by
streaming it through the production pipeline and grading against logged ground
truth. It powers Analytics and Reports.

It runs on demand against recorded data and never feeds the dashboard, so it is
an analysis capability rather than an operating mode. The rename removed the
collision with the old Replay mode.

## Known finding

`sensor_fault` currently **fails**: a flow-meter dropout (Qout reads 0 while
Qin is healthy) produces 8 false-positive samples. Using flow alone, a dropout
is genuinely indistinguishable from "all the water is escaping".

The deeper cause is that **mass balance and CUSUM are not independent** — both
consume the same residual, so two flow-derived detectors agreeing is enough to
trip fusion even though current and pressure both say normal. A fix would
require either a plausibility guard on implausible readings or a fusion rule
demanding corroboration from a non-flow channel.

This is left visible rather than silenced. A failing scenario is a finding.
