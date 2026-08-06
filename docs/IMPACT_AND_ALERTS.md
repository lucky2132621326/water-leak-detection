# Impact Analysis, Alert Center & Automatic Reports

Detection answers *"is there a leak?"*. This subsystem answers the question an
operator or municipality actually asks next: **"so what, and what do I do about
it?"**

It turns one number — the estimated leak rate — into litres, rupees, a severity
category, a repair-urgency recommendation, a durable incident record, and a
publishable report.

---

## 1. Where the leak rate comes from

The detection pipeline already computes a **flow residual**:

```
residual = Qin − (Qout + Qbranch)
```

That residual *is* the estimated leak rate: water that entered the zone and
never left it. `AlertService.leak_rate_from()` is the single place that
converts a detection response into a leak rate, clamped at zero — a negative
residual means more water left than entered, which is a sensor artefact, not a
negative leak.

Everything downstream consumes that one number, so no two screens can disagree
about how big a leak is.

---

## 2. Impact engine (`backend/impact/`)

| Module | Responsibility |
|---|---|
| `water_loss.py` | L/min → litres per hour / day / week / month / year, plus relatable equivalents |
| `cost_estimator.py` | Applies the volumetric tariff (quoted per **kilolitre**, as municipal slabs are) |
| `severity.py` | Band classification + repair-urgency recommendation |
| `progression.py` | "What if nobody fixes this?" cumulative projection |
| `impact_service.py` | Composes the four; the only entry point callers should use |

All four are pure arithmetic — no I/O, no database — so they are cheap enough to
call on every telemetry sample and trivially unit-testable.

### Worked example — 0.62 L/min at ₹20/kL

```
0.62 L/min
  → 37.2 L/hour
  → 892.8 L/day        ₹17.86/day
  → 26,784 L/month     ₹535.68/month
  → 326,040 L/year     ₹6,517.44/year
severity: MAJOR   urgency: URGENT ("repair within 7 days")
```

### Severity bands

Configured in `backend/config/impact.yaml`. Upper bounds are **exclusive**, so
no rate can fall into two bands (0.2 is MODERATE, not MINOR).

| Band | Range (L/min) |
|---|---|
| 🟢 MINOR | 0 – 0.2 |
| 🟡 MODERATE | 0.2 – 0.5 |
| 🟠 MAJOR | 0.5 – 1.0 |
| 🔴 CRITICAL | 1.0+ |

### Guardrail

The recommendation output is **scheduling advice only** — "repair within 7 days",
"dispatch a crew for field verification". It never instructs anyone to operate a
valve or pump, consistent with the project-wide constraint. This is enforced by
a test (`test_recommendation_never_issues_control_instructions`), not just by
convention.

### Progression assumptions

The simulator assumes a **constant** leak rate over the whole horizon and says
so in its own `assumptions` field. Real leaks worsen over time, so every
projection is a conservative lower bound — which is the defensible direction to
err in.

---

## 3. Alert Center (`backend/alerts/`)

The pipeline emits a response *per sample*. An operator works in *incidents*.
`AlertService` bridges the two.

### Lifecycle

```
                  ┌──────────────────┐
  alarm sample ──▶│      ACTIVE      │──── operator: repaired ──▶ RESOLVED
                  │  (needs action)  │──── operator: no leak ───▶ FALSE_POSITIVE
                  └──────────────────┘◀─── reopen ───────────────┘
```

`is_open` is tracked **separately** from `status`. An incident whose alarm has
cleared can still be ACTIVE: the water stopped registering, but nobody has
verified or repaired anything yet.

### Aggregation rules

- Consecutive alarm samples within `merge_gap_sec` (default 30 s) merge into one
  incident.
- **Peak** rate is retained, not the last value — severity and savings should
  reflect the worst of the incident.
- Re-ingesting a timestamp an incident already covers **updates** that incident
  rather than creating a new one. This matters because the replay player loops a
  stored run continuously; without it, one seeded leak window would produce a
  new alert every pass. Matching is on window *overlap* rather than exact onset,
  because detector warm-up state carries across loops and the confirmed onset
  drifts slightly.
- Replaying evidence never undoes an operator's disposition.

### Storage

MongoDB `alerts` collection, with an authoritative in-memory mirror. Writes are
best-effort persisted and reloaded on restart; if Mongo is unreachable the
service degrades to memory-only rather than failing the request. Pass
`enable_persistence=False` for a pure in-memory instance (the test suite does).

---

## 4. Water Savings counter

When an incident is marked RESOLVED, the water it *would have* kept losing is
credited as prevented:

```
saved = peak_leak_rate × prevented_horizon (default 30 days)
```

- Dismissed false positives are **never** credited.
- Reopening an incident reverses the credit.
- `detection_precision` = resolved ÷ (resolved + false positives), i.e. measured
  from real operator dispositions rather than assumed.

The 30-day horizon is deliberately short: long enough to be meaningful, short
enough that the figure isn't an unfalsifiable annualised claim.

---

## 5. Automatic experiment reports (`backend/reports/`)

`ExperimentReportGenerator.build(run_id)` assembles:

1. **Experiment info** — operator, date, duration, sample count
2. **Leak events** — ground-truth windows with per-event impact and volume lost
3. **Detection results** — precision / recall / F1 / latency, scored by replaying
   every stored sample through the production `DetectionPipeline` against logged
   ground truth. Nothing here is hardcoded.
4. **Graphs** — residual, Qin, Qout and motor current, with leak windows shaded
5. **Quantified impact** — the largest leak's projected loss
6. **Conclusions** — auto-generated, each stating the number it rests on

`render_html()` produces a standalone printable document. There is no PDF
library: the browser's *Save as PDF* is the export path, which keeps the report
a single self-contained file that prints correctly offline and stays readable in
the repo. Charts are hand-rolled inline SVG for the same reason.

---

## 6. API surface

| Route | Purpose |
|---|---|
| `GET /api/impact/config` | Tariff, severity bands, simulator options |
| `GET /api/impact/current` | Impact of whatever the detector sees right now |
| `POST /api/impact/simulate` | Interactive what-if (`leak_rate_lpm`, `repair_delay_days`, `tariff_per_kl`) |
| `GET /api/alerts` | Incident list; filters: `status`, `zone`, `severity`, `min_confidence`, `since_ts`, `until_ts`, `search`, `limit` |
| `GET /api/alerts/summary` | Counts, known zones, monthly timeline |
| `POST /api/alerts/:id/resolve` | Mark repaired (credits savings) |
| `POST /api/alerts/:id/false-positive` | Dismiss (credits nothing) |
| `POST /api/alerts/:id/reopen` | Undo a disposition |
| `GET /api/savings` | Water Savings KPI |
| `GET /api/reports/experiment/:run_id` | Structured report JSON |
| `GET /api/reports/experiment/:run_id/html` | Printable / Save-as-PDF document |

`/api/telemetry` also carries `leak_rate_lpm` and an `impact` summary, so every
view polling it shows figures consistent with the Alert Center.

---

## 7. Dashboard views

- **Dashboard** — impact strip: water loss, annual cost, severity badge, savings KPI
- **Impact Simulator** — the interactive "what if we ignore it?" screen
- **Alert Center** — incident queue with disposition actions
- **Leak History** — filtered investigation over past incidents + monthly trend
- **Reports** — generate and open experiment reports

Every figure is fetched from the backend; none is computed in the browser, so
the UI cannot quote a number the detection pipeline wouldn't.

---

## 8. Operator workflow

```
Detect → Classify severity → Quantify loss & cost → Triage in Alert Center
  → Dispatch work order → Mark repaired → Savings KPI → Report
```

---

## 9. Tests

```bash
python -m unittest tests.test_impact tests.test_alert_service
```

39 tests covering the loss/cost arithmetic, band boundaries, the control-language
guardrail, progression monotonicity, incident merging, replay idempotency,
savings crediting and reversal, and every query filter. The alert tests require
no MongoDB.

---

## 10. Limitations

- Impact figures are **indicative**; field verification is required before any
  repair action.
- Projections assume a constant leak rate (see §2).
- Savings are a modelled counterfactual over a 30-day horizon, not metered
  recovery.
- Severity is derived from flow residual alone; there is no pressure-sensor
  input to corroborate it on the current rig.
