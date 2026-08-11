"""Experiment Report Generator

One call produces the whole write-up for a stored run. Every number in it is
computed from real stored telemetry and real ground-truth leak events scored
through the same DetectionPipeline the live system uses — nothing here is
hand-authored, which is the point: the report is evidence, not a brochure.
"""
import html
import time

from backend.repositories.telemetry_repository import TelemetryRepository
from backend.repositories.detection_repository import LeakEventRepository
from backend.benchmark.benchmark_scorer import BenchmarkScorer
from backend.impact.impact_service import ImpactService
from backend.reports.charts import line_chart
from backend.repositories.db import get_db
from backend.utils.logger import logger
from backend.detectors.residual import compute_residual

_DISCLAIMER = (
    "Detection results are indicative and require field verification. This report "
    "contains no valve or pump control instructions; repair-urgency guidance is "
    "scheduling advice only."
)


class ExperimentReportGenerator:
    def __init__(self, db=None, impact_service: ImpactService = None):
        self.db = db if db is not None else get_db()
        self.telemetry_repo = TelemetryRepository(self.db)
        self.leak_event_repo = LeakEventRepository(self.db)
        self.impact = impact_service or ImpactService()

    # --- data assembly ----------------------------------------------------
    def build(self, run_id: str) -> dict:
        run_meta = self.db.experiment_runs.find_one({"run_id": run_id}, {"_id": 0})
        telemetry = self.telemetry_repo.get_by_run(run_id)

        if not telemetry:
            return {"run_id": run_id, "error": f"No stored telemetry for run '{run_id}'."}

        leak_events = self.leak_event_repo.get_for_run(run_id)
        evaluation = BenchmarkScorer().run(run_id)
        metrics = evaluation.get("metrics") or {}

        start_ts = telemetry[0]["ts"]
        end_ts = telemetry[-1]["ts"]

        series = self._series(telemetry)
        events = self._events(leak_events, start_ts)
        impact = self.impact.analyze(max((e["severity_lpm"] for e in events), default=0.0))

        report = {
            "run_id": run_id,
            "generated_at": time.time(),
            "generated_at_human": time.strftime("%d %b %Y, %H:%M:%S"),
            "info": {
                "run_id": run_id,
                "operator": (run_meta or {}).get("operator", "unknown"),
                "date": (run_meta or {}).get("date", time.strftime("%Y-%m-%d", time.localtime(start_ts))),
                "duration_sec": int(round(end_ts - start_ts)),
                "sample_count": len(telemetry),
                "pump_mode": (run_meta or {}).get("pump_mode", "constant"),
                "location": (run_meta or {}).get("location", "—"),
                "notes": (run_meta or {}).get("notes", ""),
                "start_ts": start_ts,
                "end_ts": end_ts,
            },
            "leak_events": events,
            "metrics": metrics,
            "series": series,
            "impact": impact,
            "conclusions": self._conclusions(events, metrics, impact),
            "disclaimer": _DISCLAIMER,
        }
        logger.info(f"[Report] Built experiment report for run_id={run_id}")
        return report

    @staticmethod
    def _series(telemetry):
        out = {"ts": [], "q_in": [], "q_out": [], "q_branch": [], "residual": [], "current_ma": [], "band_mid": []}
        for d in telemetry:
            flow, power = d.get("flow", {}), d.get("power", {})
            q_in = flow.get("q_in_lpm", 0.0)
            q_out = flow.get("q_out_lpm", 0.0)
            q_branch = flow.get("q_branch_lpm", 0.0)
            out["ts"].append(d["ts"])
            out["q_in"].append(round(q_in, 3))
            out["q_out"].append(round(q_out, 3))
            out["q_branch"].append(round(q_branch, 3))
            out["residual"].append(round(compute_residual(q_in, q_out, q_branch), 3))
            out["current_ma"].append(round(power.get("current_ma", 0.0), 1))
            out["band_mid"].append((d.get("vibration") or {}).get("band_mid"))
        return out

    def _events(self, leak_events, run_start_ts):
        events = []
        for e in leak_events:
            start = e.get("open_ts", e.get("start_ts"))
            stop = e.get("close_ts", e.get("stop_ts"))
            duration = (stop - start) if (start is not None and stop is not None) else None
            severity = float(e.get("leak_lpm", e.get("severity_lpm")) or 0.0)
            events.append({
                "location_node": e.get("location_node", e.get("tee_id", "—")),
                "severity_lpm": round(severity, 3),
                "start_ts": start,
                "stop_ts": stop,
                "start_offset_sec": int(round(start - run_start_ts)) if start is not None else None,
                "duration_sec": int(round(duration)) if duration is not None else None,
                "is_ground_truth": bool(e.get("is_ground_truth")),
                "notes": e.get("notes", ""),
                "impact": self.impact.summarize(severity),
                "volume_lost_litres": round(severity * (duration / 60.0), 1) if duration else None,
            })
        return events

    @staticmethod
    def _conclusions(events, metrics, impact):
        """Auto-generated findings. Each line states the number it rests on so a
        reader can check the claim against the tables above it."""
        out = []

        if not metrics:
            return ["Insufficient data to score detector performance for this run."]

        recall = metrics.get("recall")
        precision = metrics.get("precision")
        f1 = metrics.get("f1_score")
        latency = metrics.get("avg_latency_sec")
        fp = metrics.get("false_positives", 0)

        if events:
            sizes = [e["severity_lpm"] for e in events]
            smallest, largest = min(sizes), max(sizes)
            out.append(
                f"{len(events)} ground-truth leak event(s) were injected, ranging "
                f"{smallest:.2f}–{largest:.2f} L/min."
            )
            if recall is not None and recall >= 0.99:
                out.append(f"All injected leaks at or above {smallest:.2f} L/min were detected (recall {recall:.1%}).")
            elif recall is not None:
                out.append(f"Detection recall was {recall:.1%} — {metrics.get('false_negatives', 0)} leak sample(s) were missed.")
        else:
            out.append("No ground-truth leak events were logged for this run; it is treated as a clean-baseline run.")

        if precision is not None:
            if fp == 0:
                out.append(f"No false positives were raised across {metrics.get('true_negatives', 0)} clean samples (precision {precision:.1%}).")
            else:
                out.append(f"{fp} false-positive sample(s) were raised (precision {precision:.1%}); review detector thresholds before field deployment.")

        if latency is not None:
            out.append(f"Mean detection latency was {latency:.1f} s from leak onset to confirmed alarm.")
        elif events:
            out.append("No leak was confirmed within the run window, so detection latency could not be measured.")

        if f1 is not None:
            verdict = "meets" if f1 >= 0.8 else "falls short of" if f1 < 0.6 else "approaches"
            out.append(f"Overall F1 of {f1:.3f} {verdict} the 0.80 target for this configuration.")

        if impact and impact.get("leak_rate_lpm", 0) > 0:
            wl, cost = impact["water_loss"], impact["cost"]
            out.append(
                f"Left unrepaired, the largest leak in this run would waste "
                f"{wl['litres_per_day']:,.0f} L/day ({cost['currency_symbol']}{cost['cost_per_year']:,.0f}/year "
                f"at the configured tariff), classified {impact['severity']['label']}."
            )

        out.append("Results are indicative; field verification is required before any repair action.")
        return out

    # --- HTML rendering ---------------------------------------------------
    @staticmethod
    def _event_row(e: dict) -> str:
        onset = "—" if e["start_offset_sec"] is None else f"T+{e['start_offset_sec']}s"
        duration = "—" if e["duration_sec"] is None else f"{e['duration_sec']} s"
        volume = "—" if e["volume_lost_litres"] is None else f"{e['volume_lost_litres']:,.1f} L"
        severity = e["impact"]["severity"]
        color = e["impact"]["severity_color"]
        source = "ground truth" if e["is_ground_truth"] else "observed"
        return (
            f"<tr><td><strong>{html.escape(str(e['location_node']))}</strong></td>"
            f"<td>{e['severity_lpm']:.2f} L/min</td>"
            f"<td>{onset}</td><td>{duration}</td><td>{volume}</td>"
            f"<td><span class='badge badge-{html.escape(color)}'>{html.escape(severity)}</span></td>"
            f"<td>{source}</td></tr>"
        )

    def render_html(self, report: dict) -> str:
        if report.get("error"):
            return f"<main class='report'><h1>Report unavailable</h1><p>{html.escape(report['error'])}</p></main>"

        info, metrics, impact = report["info"], report["metrics"], report["impact"]
        series = report["series"]
        ts = series["ts"]

        leak_spans = [
            (e["start_ts"], e["stop_ts"])
            for e in report["leak_events"]
            if e.get("start_ts") is not None and e.get("stop_ts") is not None
        ]

        charts = "".join([
            line_chart(list(zip(ts, series["residual"])), "Flow Residual (Qin − Qout − Qbranch)",
                       "residual", color="#dc2626", shaded_spans=leak_spans, unit="L/min"),
            line_chart(list(zip(ts, series["q_in"])), "Inlet Flow (Qin)",
                       "flow", color="#2563eb", shaded_spans=leak_spans, unit="L/min"),
            line_chart(list(zip(ts, series["q_out"])), "Outlet Flow (Qout)",
                       "flow", color="#0891b2", shaded_spans=leak_spans, unit="L/min"),
            line_chart(list(zip(ts, series["current_ma"])), "Pump Motor Current",
                       "current", color="#7c3aed", shaded_spans=leak_spans, unit="mA"),
        ])

        events_rows = "".join(self._event_row(e) for e in report["leak_events"]) or (
            "<tr><td colspan='7' class='muted'>No leak events logged for this run.</td></tr>"
        )

        def metric_card(label, value, sub=""):
            return (f"<div class='metric'><span class='metric-label'>{html.escape(label)}</span>"
                    f"<span class='metric-value'>{html.escape(str(value))}</span>"
                    f"<span class='metric-sub'>{html.escape(sub)}</span></div>")

        def pct(v):
            return "—" if v is None else f"{v * 100:.1f}%"

        metrics_html = "".join([
            metric_card("Precision", pct(metrics.get("precision")), f"{metrics.get('false_positives', 0)} false positives"),
            metric_card("Recall", pct(metrics.get("recall")), f"{metrics.get('false_negatives', 0)} missed samples"),
            metric_card("F1 Score", f"{metrics.get('f1_score', 0):.3f}" if metrics.get("f1_score") is not None else "—", "harmonic mean"),
            metric_card("Detection Latency",
                        "—" if metrics.get("avg_latency_sec") is None else f"{metrics['avg_latency_sec']:.1f} s",
                        "leak onset → confirmed alarm"),
            metric_card("True Positives", metrics.get("true_positives", 0), "alarm samples inside a leak window"),
            metric_card("True Negatives", metrics.get("true_negatives", 0), "quiet samples correctly ignored"),
        ])

        cost, wl = impact["cost"], impact["water_loss"]
        cs = cost["currency_symbol"]
        impact_html = "".join([
            metric_card("Peak Leak Rate", f"{impact['leak_rate_lpm']:.2f} L/min", impact["severity"]["label"]),
            metric_card("Daily Loss", f"{wl['litres_per_day']:,.0f} L", f"{cs}{cost['cost_per_day']:,.2f}/day"),
            metric_card("Monthly Loss", f"{wl['litres_per_month']:,.0f} L", f"{cs}{cost['cost_per_month']:,.2f}/month"),
            metric_card("Annual Loss", f"{wl['litres_per_year']:,.0f} L", f"{cs}{cost['cost_per_year']:,.2f}/year"),
        ])

        conclusions_html = "".join(f"<li>{html.escape(c)}</li>" for c in report["conclusions"])

        info_rows = "".join(
            f"<tr><th>{html.escape(k)}</th><td>{html.escape(str(v))}</td></tr>"
            for k, v in [
                ("Run ID", info["run_id"]),
                ("Operator", info["operator"]),
                ("Date", info["date"]),
                ("Duration", f"{info['duration_sec']} s"),
                ("Samples", f"{info['sample_count']:,}"),
                ("Pump Mode", info["pump_mode"]),
                ("Location", info["location"]),
                ("Notes", info["notes"] or "—"),
            ]
        )

        return f"""<main class="report">
  <header class="report-header">
    <div>
      <p class="eyebrow">Automatic Experiment Report</p>
      <h1>Run {html.escape(info['run_id'])}</h1>
      <p class="muted">Generated {html.escape(report['generated_at_human'])} · Water Distribution Leakage Detection</p>
    </div>
    <button class="print-btn no-print" onclick="window.print()">Save as PDF</button>
  </header>

  <section>
    <h2>1. Experiment Information</h2>
    <table class="kv">{info_rows}</table>
  </section>

  <section>
    <h2>2. Leak Events</h2>
    <table class="data">
      <thead><tr><th>Location</th><th>Rate</th><th>Onset</th><th>Duration</th><th>Volume Lost</th><th>Severity</th><th>Source</th></tr></thead>
      <tbody>{events_rows}</tbody>
    </table>
  </section>

  <section>
    <h2>3. Detection Results</h2>
    <div class="metric-grid">{metrics_html}</div>
    <p class="muted small">Scored by replaying every stored sample through the production DetectionPipeline and comparing against logged ground-truth leak windows.</p>
  </section>

  <section>
    <h2>4. Telemetry Graphs</h2>
    <p class="muted small">Shaded bands mark ground-truth leak windows.</p>
    {charts}
  </section>

  <section>
    <h2>5. Quantified Impact</h2>
    <div class="metric-grid">{impact_html}</div>
    <p class="muted small">{html.escape(impact['recommendation']['headline'])} — {html.escape(impact['recommendation']['action'])}</p>
  </section>

  <section>
    <h2>6. Conclusions</h2>
    <ol class="conclusions">{conclusions_html}</ol>
  </section>

  <footer class="disclaimer">{html.escape(report['disclaimer'])}</footer>
</main>
{_REPORT_CSS}"""


_REPORT_CSS = """<style>
  :root { color-scheme: light; }
  body { margin: 0; background: #f1f5f9; }
  .report { max-width: 860px; margin: 0 auto; padding: 40px 44px 64px; background: #fff;
            font: 14px/1.6 ui-sans-serif, system-ui, -apple-system, "Segoe UI", sans-serif; color: #1e293b; }
  .report-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 24px;
                   border-bottom: 3px solid #2563eb; padding-bottom: 20px; margin-bottom: 8px; }
  .eyebrow { text-transform: uppercase; letter-spacing: .08em; font-size: 11px; font-weight: 700;
             color: #2563eb; margin: 0 0 4px; }
  h1 { font-size: 30px; margin: 0 0 6px; letter-spacing: -0.02em; }
  h2 { font-size: 17px; margin: 34px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #e2e8f0; }
  .muted { color: #64748b; margin: 4px 0; }
  .small { font-size: 12px; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  table.kv th { text-align: left; width: 180px; color: #64748b; font-weight: 600; padding: 7px 0; vertical-align: top; }
  table.kv td { padding: 7px 0; }
  table.kv tr + tr th, table.kv tr + tr td { border-top: 1px solid #f1f5f9; }
  table.data th { text-align: left; background: #f8fafc; padding: 9px 10px; font-size: 11px;
                  text-transform: uppercase; letter-spacing: .04em; color: #475569; border-bottom: 1px solid #e2e8f0; }
  table.data td { padding: 9px 10px; border-bottom: 1px solid #f1f5f9; }
  .metric-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-top: 6px; }
  .metric { border: 1px solid #e2e8f0; border-radius: 12px; padding: 14px 16px; background: #f8fafc; }
  .metric-label { display: block; font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: #64748b; font-weight: 700; }
  .metric-value { display: block; font-size: 24px; font-weight: 700; color: #0f172a; margin: 4px 0 2px; letter-spacing: -0.02em; }
  .metric-sub { display: block; font-size: 11px; color: #94a3b8; }
  .badge { display: inline-block; padding: 2px 9px; border-radius: 999px; font-size: 11px; font-weight: 700; }
  .badge-slate { background: #e2e8f0; color: #334155; }
  .badge-emerald { background: #d1fae5; color: #065f46; }
  .badge-amber { background: #fef3c7; color: #92400e; }
  .badge-orange { background: #ffedd5; color: #9a3412; }
  .badge-rose { background: #ffe4e6; color: #9f1239; }
  .chart-block { margin: 18px 0 26px; }
  .chart-block figcaption { display: flex; justify-content: space-between; align-items: baseline;
                            font-size: 13px; margin-bottom: 6px; gap: 12px; }
  .chart-axis-note { color: #94a3b8; font-size: 11px; }
  .chart { width: 100%; height: auto; border: 1px solid #e2e8f0; border-radius: 10px; background: #fff; }
  .chart-empty { padding: 24px; text-align: center; color: #94a3b8; border: 1px dashed #cbd5e1; border-radius: 10px; }
  .axis-label { font-size: 10px; fill: #94a3b8; }
  .conclusions { padding-left: 20px; }
  .conclusions li { margin-bottom: 8px; }
  .disclaimer { margin-top: 36px; padding: 14px 16px; background: #fffbeb; border: 1px solid #fde68a;
                border-radius: 10px; font-size: 12px; color: #92400e; }
  .print-btn { flex-shrink: 0; background: #2563eb; color: #fff; border: 0; border-radius: 10px;
               padding: 10px 18px; font-size: 13px; font-weight: 700; cursor: pointer; }
  .print-btn:hover { background: #1d4ed8; }
  @media print {
    body { background: #fff; }
    .no-print { display: none; }
    .report { max-width: none; padding: 0; }
    section { break-inside: avoid; }
    .chart-block { break-inside: avoid; }
  }
</style>"""
