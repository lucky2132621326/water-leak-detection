import React, { useEffect, useState } from "react";
import {
  FileText, ExternalLink, Loader2, FlaskConical, Target, Timer, Droplets,
  IndianRupee, CheckCircle2, AlertTriangle, Printer
} from "lucide-react";
import type { ExperimentReport, ReplayRun } from "../types";
import { formatLitres, formatMoney, formatRate, severityStyle } from "../lib/impact";

/**
 * Automatic Experiment Report — one click turns a stored run into a complete
 * research write-up.
 *
 * The structured summary here and the printable document at
 * /api/reports/experiment/:id/html are generated from the same backend call, so
 * what an operator reads on screen is exactly what gets saved as a PDF.
 */
export const ReportsView: React.FC = () => {
  const [runs, setRuns] = useState<ReplayRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [report, setReport] = useState<ExperimentReport | null>(null);
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/replay/runs")
      .then((r) => r.json())
      .then((data) => {
        const rows: ReplayRun[] = Array.isArray(data) ? data : [];
        setRuns(rows);
        if (rows.length > 0) setSelectedRun(rows[0].run_id);
      })
      .catch(() => setError("Could not load stored experiment runs."));
  }, []);

  const generate = (runId: string) => {
    setGenerating(true);
    setError(null);
    fetch(`/api/reports/experiment/${encodeURIComponent(runId)}`)
      .then((r) => r.json())
      .then((data: ExperimentReport) => {
        if (data?.error) {
          setError(data.error);
          setReport(null);
        } else {
          setReport(data);
        }
      })
      .catch(() => setError("Report generation failed — is the detection backend running?"))
      .finally(() => setGenerating(false));
  };

  const metrics = report?.metrics;
  const impact = report?.impact;
  const symbol = impact?.cost.currency_symbol ?? "₹";
  const pct = (v?: number) => (v === undefined || v === null ? "—" : `${(v * 100).toFixed(1)}%`);

  return (
    <div className="space-y-6">
      {/* Run picker */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
              <FileText className="w-6 h-6 text-blue-600" />
              <span>Automatic Experiment Reports</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1 max-w-2xl">
              Generate a complete research write-up for any stored run — metadata, leak events,
              detector performance, telemetry graphs, quantified impact and auto-written conclusions.
            </p>
          </div>
          {selectedRun && (
            <div className="flex items-center space-x-2 shrink-0">
              <button
                onClick={() => generate(selectedRun)}
                disabled={generating}
                className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-bold rounded-xl shadow-2xs flex items-center space-x-2 transition"
              >
                {generating ? <Loader2 className="w-4 h-4 animate-spin" /> : <FlaskConical className="w-4 h-4" />}
                <span>{generating ? "Generating…" : "Generate Report"}</span>
              </button>
              <a
                href={`/api/reports/experiment/${encodeURIComponent(selectedRun)}/html`}
                target="_blank"
                rel="noreferrer"
                className="px-4 py-2.5 bg-white border border-slate-200 hover:border-blue-300 hover:text-blue-600 text-slate-700 text-xs font-bold rounded-xl shadow-2xs flex items-center space-x-2 transition"
              >
                <Printer className="w-4 h-4" />
                <span>Open Printable / PDF</span>
              </a>
            </div>
          )}
        </div>

        {error && (
          <p className="mb-4 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-2.5 font-medium">{error}</p>
        )}

        {runs.length === 0 ? (
          <div className="py-10 text-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
            No stored experiment runs. Seed one with <code className="font-mono text-slate-600">python -m backend.replay.seed_runs</code>.
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {runs.map((run) => {
              const active = selectedRun === run.run_id;
              return (
                <button
                  key={run.run_id}
                  onClick={() => { setSelectedRun(run.run_id); setReport(null); }}
                  className={`text-left rounded-2xl border p-4 transition ${
                    active ? "border-blue-400 bg-blue-50/60 shadow-2xs" : "border-slate-200 bg-white hover:border-blue-200"
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <h4 className="text-sm font-extrabold text-slate-800">{run.run_id}</h4>
                    {active && <span className="px-2 py-0.5 rounded-md text-[10px] font-extrabold bg-blue-600 text-white">SELECTED</span>}
                  </div>
                  <p className="text-[11px] text-slate-500 font-medium mt-1.5">
                    {run.date} · {run.operator} · {run.duration_sec}s
                  </p>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    {run.location} · injected leak {Number(run.leak_size_lpm ?? 0).toFixed(2)} L/min
                  </p>
                </button>
              );
            })}
          </div>
        )}
      </div>

      {/* Generated report summary */}
      {report && !report.error && (
        <>
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
            <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
              <div>
                <h3 className="text-lg font-bold text-slate-900">Report · {report.info.run_id}</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Generated {report.generated_at_human} · {report.info.sample_count.toLocaleString()} samples over {report.info.duration_sec}s
                  · operator {report.info.operator}
                </p>
              </div>
              <a
                href={`/api/reports/experiment/${encodeURIComponent(report.run_id)}/html`}
                target="_blank"
                rel="noreferrer"
                className="text-xs font-bold text-blue-600 hover:text-blue-700 flex items-center space-x-1.5 shrink-0"
              >
                <span>View full document</span><ExternalLink className="w-3.5 h-3.5" />
              </a>
            </div>

            {/* Detection metrics */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
              <StatTile icon={<Target className="w-4 h-4" />} label="Precision" value={pct(metrics?.precision)} sub={`${metrics?.false_positives ?? 0} false positives`} tone="emerald" />
              <StatTile icon={<Target className="w-4 h-4" />} label="Recall" value={pct(metrics?.recall)} sub={`${metrics?.false_negatives ?? 0} missed samples`} tone="blue" />
              <StatTile icon={<CheckCircle2 className="w-4 h-4" />} label="F1 Score" value={metrics?.f1_score !== undefined ? metrics.f1_score.toFixed(3) : "—"} sub="harmonic mean" tone="indigo" />
              <StatTile icon={<Timer className="w-4 h-4" />} label="Latency" value={metrics?.avg_latency_sec != null ? `${metrics.avg_latency_sec.toFixed(1)}s` : "—"} sub="onset → confirmed" tone="amber" />
            </div>
          </div>

          {/* Leak events */}
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-4">Leak Events</h3>
            {report.leak_events.length === 0 ? (
              <p className="text-xs text-slate-400 py-6 text-center border border-dashed border-slate-200 rounded-xl">
                No leak events logged — treated as a clean-baseline run.
              </p>
            ) : (
              <div className="overflow-x-auto -mx-6 px-6">
                <table className="w-full text-xs min-w-[700px]">
                  <thead>
                    <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-200">
                      <th className="py-2.5 pr-4 font-extrabold">Location</th>
                      <th className="py-2.5 pr-4 font-extrabold">Rate</th>
                      <th className="py-2.5 pr-4 font-extrabold">Onset</th>
                      <th className="py-2.5 pr-4 font-extrabold">Duration</th>
                      <th className="py-2.5 pr-4 font-extrabold">Volume Lost</th>
                      <th className="py-2.5 pr-4 font-extrabold">Severity</th>
                      <th className="py-2.5 font-extrabold">Source</th>
                    </tr>
                  </thead>
                  <tbody>
                    {report.leak_events.map((e, i) => {
                      const sev = severityStyle(e.impact?.severity);
                      return (
                        <tr key={i} className="border-b border-slate-100">
                          <td className="py-3 pr-4 font-bold text-slate-800">{e.location_node}</td>
                          <td className="py-3 pr-4 font-mono text-slate-700">{formatRate(e.severity_lpm)}</td>
                          <td className="py-3 pr-4 text-slate-500">{e.start_offset_sec !== null ? `T+${e.start_offset_sec}s` : "—"}</td>
                          <td className="py-3 pr-4 text-slate-500">{e.duration_sec !== null ? `${e.duration_sec}s` : "—"}</td>
                          <td className="py-3 pr-4 text-slate-700 font-semibold">{e.volume_lost_litres !== null ? formatLitres(e.volume_lost_litres) : "—"}</td>
                          <td className="py-3 pr-4">
                            <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold border ${sev.badge}`}>
                              {sev.emoji} {e.impact?.severity ?? "—"}
                            </span>
                          </td>
                          <td className="py-3 text-slate-400">{e.is_ground_truth ? "ground truth" : "observed"}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          {/* Impact + conclusions */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
              <h3 className="text-sm font-bold text-slate-900 mb-4">Quantified Impact</h3>
              <div className="grid grid-cols-2 gap-4">
                <StatTile icon={<Droplets className="w-4 h-4" />} label="Peak Rate" value={formatRate(impact?.leak_rate_lpm)} sub={impact?.severity.label ?? "—"} tone="blue" />
                <StatTile icon={<Droplets className="w-4 h-4" />} label="Daily Loss" value={formatLitres(impact?.water_loss.litres_per_day, { compact: true })} sub={formatMoney(impact?.cost.cost_per_day, symbol) + "/day"} tone="indigo" />
                <StatTile icon={<IndianRupee className="w-4 h-4" />} label="Monthly Cost" value={formatMoney(impact?.cost.cost_per_month, symbol, { compact: true })} sub={formatLitres(impact?.water_loss.litres_per_month, { compact: true })} tone="amber" />
                <StatTile icon={<IndianRupee className="w-4 h-4" />} label="Annual Cost" value={formatMoney(impact?.cost.cost_per_year, symbol, { compact: true })} sub={formatLitres(impact?.water_loss.litres_per_year, { compact: true })} tone="rose" />
              </div>
              {impact && (
                <p className="mt-4 text-xs text-slate-500 leading-relaxed border-t border-slate-100 pt-4">
                  <strong className="text-slate-700">{impact.recommendation.headline}.</strong> {impact.recommendation.action}
                </p>
              )}
            </div>

            <div className="lg:col-span-7 bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
              <h3 className="text-sm font-bold text-slate-900 mb-4">Auto-Generated Conclusions</h3>
              <ol className="space-y-3">
                {report.conclusions.map((c, i) => (
                  <li key={i} className="flex items-start space-x-3">
                    <span className="w-5 h-5 rounded-lg bg-blue-100 text-blue-700 text-[10px] font-extrabold flex items-center justify-center shrink-0 mt-0.5">
                      {i + 1}
                    </span>
                    <p className="text-xs text-slate-600 leading-relaxed">{c}</p>
                  </li>
                ))}
              </ol>
            </div>
          </div>

          <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 flex items-start space-x-2.5">
            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <p className="text-xs text-amber-800 font-medium leading-relaxed">{report.disclaimer}</p>
          </div>
        </>
      )}
    </div>
  );
};

const TILE_TONES: Record<string, string> = {
  emerald: "bg-emerald-50 border-emerald-100 text-emerald-600",
  blue: "bg-blue-50 border-blue-100 text-blue-600",
  indigo: "bg-indigo-50 border-indigo-100 text-indigo-600",
  amber: "bg-amber-50 border-amber-100 text-amber-600",
  rose: "bg-rose-50 border-rose-100 text-rose-600",
};

const StatTile: React.FC<{ icon: React.ReactNode; label: string; value: string; sub: string; tone: string }> = ({
  icon, label, value, sub, tone,
}) => (
  <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-4">
    <div className={`w-8 h-8 rounded-xl border flex items-center justify-center mb-2.5 ${TILE_TONES[tone]}`}>{icon}</div>
    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">{label}</p>
    <p className="text-xl font-extrabold text-slate-900 tracking-tight mt-0.5">{value}</p>
    <p className="text-[11px] text-slate-400 font-medium mt-0.5">{sub}</p>
  </div>
);
