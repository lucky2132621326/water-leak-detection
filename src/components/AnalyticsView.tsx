import React, { useCallback, useEffect, useState } from "react";
import {
  BarChart3, Target, Timer, Activity, RefreshCw, Loader2, FlaskConical, Info, AlertTriangle
} from "lucide-react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid,
  BarChart, Bar, Legend
} from "recharts";

interface Overall {
  precision: number | null; recall: number | null; f1_score: number | null;
  median_latency_sec: number | null; true_positives: number; false_positives: number;
  false_negatives: number; true_negatives: number; sample_count: number;
}
interface MethodRow {
  method: string; key: string; precision: number | null; recall: number | null;
  median_latency_sec: number | null; false_positives: number;
}
interface SensitivityRow {
  leak_size_lpm: number; runs: number; recall: number | null; precision: number | null;
}
interface Summary {
  has_data: boolean; reason?: string; run_count: number;
  overall: Overall | null; per_method: MethodRow[]; sensitivity: SensitivityRow[];
  runs: any[]; basis?: string;
}
interface Roc {
  has_data: boolean; reason?: string; auc: number | null;
  points: { threshold: number; tpr: number; fpr: number }[]; sample_count?: number;
}

/**
 * Benchmark analytics.
 *
 * Every figure is fetched from /api/analytics/*, which recomputes it by
 * replaying stored runs through the production pipeline. Nothing here is
 * authored — if no runs exist the page says so rather than showing placeholder
 * metrics that would contradict the scenario results.
 */
export const AnalyticsView: React.FC = () => {
  const [summary, setSummary] = useState<Summary | null>(null);
  const [roc, setRoc] = useState<Roc | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((refresh = false) => {
    setLoading(true);
    const q = refresh ? "?refresh=true" : "";
    Promise.all([
      fetch(`/api/analytics/summary${q}`).then((r) => r.json()),
      fetch(`/api/analytics/roc${q}`).then((r) => r.json()),
    ])
      .then(([s, r]) => { setSummary(s); setRoc(r); setError(null); })
      .catch(() => setError("Could not reach the analytics backend."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => { load(false); }, [load]);

  const pct = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${(v * 100).toFixed(1)}%`;
  const secs = (v: number | null | undefined) =>
    v === null || v === undefined ? "—" : `${v.toFixed(1)}s`;

  const o = summary?.overall;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
              <BarChart3 className="w-6 h-6 text-blue-600" />
              <span>Benchmark Evaluation & Analytics</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1 max-w-3xl">
              {summary?.basis ??
                "Detector performance scored against logged ground-truth leak windows."}
            </p>
          </div>
          <button
            onClick={() => load(true)}
            disabled={loading}
            className="px-4 py-2.5 bg-white border border-slate-200 hover:border-blue-300 hover:text-blue-600 text-slate-700 disabled:opacity-60 text-xs font-bold rounded-xl shadow-2xs flex items-center space-x-2 transition"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
            <span>{loading ? "Scoring…" : "Re-score runs"}</span>
          </button>
        </div>
        {error && (
          <p className="mt-3 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-2.5 font-medium">{error}</p>
        )}
      </div>

      {summary && !summary.has_data ? (
        <div className="bg-white rounded-2xl border border-slate-200/80 p-12 shadow-xs text-center">
          <FlaskConical className="w-10 h-10 text-slate-300 mx-auto mb-3" />
          <h3 className="text-sm font-bold text-slate-600">No benchmark data yet</h3>
          <p className="text-xs text-slate-400 mt-1 max-w-md mx-auto">
            {summary.reason} Score a scenario from Mock Scenarios, or record a live run from Experiment Control.
          </p>
        </div>
      ) : (
        <>
          {/* Headline metrics */}
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
            <Metric label="Precision" value={pct(o?.precision)} tone="emerald"
                    sub={`${o?.false_positives ?? 0} false positives`} icon={<Target className="w-5 h-5" />} />
            <Metric label="Recall" value={pct(o?.recall)} tone="blue"
                    sub={`${o?.false_negatives ?? 0} missed samples`} icon={<Target className="w-5 h-5" />} />
            <Metric label="F1 Score" value={o?.f1_score != null ? o.f1_score.toFixed(3) : "—"} tone="cyan"
                    sub="harmonic mean of P & R" icon={<Activity className="w-5 h-5" />} />
            <Metric label="Median Latency" value={secs(o?.median_latency_sec)} tone="amber"
                    sub="leak onset → confirmed alarm" icon={<Timer className="w-5 h-5" />} />
          </div>

          <p className="text-[11px] text-slate-400 flex items-center space-x-1.5">
            <Info className="w-3.5 h-3.5 shrink-0" />
            <span>
              Scored across <strong className="text-slate-600">{summary?.run_count ?? 0}</strong> run(s),{" "}
              <strong className="text-slate-600">{o?.sample_count?.toLocaleString() ?? 0}</strong> samples
              ({o?.true_positives} TP · {o?.false_positives} FP · {o?.false_negatives} FN · {o?.true_negatives} TN).
            </span>
          </p>

          <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
            {/* ROC */}
            <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-bold text-slate-900">ROC Curve</h3>
                <span className="text-xs font-mono font-bold text-emerald-600">
                  {roc?.auc != null ? `AUC = ${roc.auc.toFixed(3)}` : "AUC = —"}
                </span>
              </div>
              {roc?.has_data ? (
                <>
                  <div className="h-64">
                    <ResponsiveContainer width="100%" height="100%">
                      <LineChart data={roc.points} margin={{ top: 5, right: 10, bottom: 5, left: -18 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                        <XAxis dataKey="fpr" type="number" domain={[0, 1]} tick={{ fontSize: 10 }}
                               stroke="#94a3b8" label={{ value: "False Positive Rate", position: "insideBottom", offset: -2, fontSize: 10, fill: "#94a3b8" }} />
                        <YAxis domain={[0, 1]} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                        <Tooltip contentStyle={{ fontSize: 11, borderRadius: 10 }}
                                 formatter={(v: any, n: any) => [Number(v).toFixed(3), n === "tpr" ? "True Positive Rate" : n]} />
                        <Line type="monotone" dataKey="tpr" stroke="#059669" strokeWidth={2.5} dot={{ r: 2 }} name="tpr" />
                      </LineChart>
                    </ResponsiveContainer>
                  </div>
                  <p className="text-[11px] text-slate-400 mt-2">
                    Fusion threshold swept 0→1 over {roc.sample_count?.toLocaleString()} real samples.
                  </p>
                </>
              ) : (
                <div className="h-64 flex items-center justify-center text-xs text-slate-400 text-center px-6">
                  {roc?.reason ?? "Not enough data to plot a ROC curve."}
                </div>
              )}
            </div>

            {/* Sensitivity by leak size */}
            <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
              <div className="flex items-center justify-between mb-4">
                <h3 className="text-sm font-bold text-slate-900">Detection Recall vs Leak Size</h3>
                <span className="text-xs font-mono text-slate-400">Sensitivity</span>
              </div>
              {(summary?.sensitivity?.length ?? 0) > 0 ? (
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={summary!.sensitivity.map((s) => ({
                      size: `${s.leak_size_lpm} LPM`,
                      Recall: s.recall != null ? Number((s.recall * 100).toFixed(1)) : 0,
                      Precision: s.precision != null ? Number((s.precision * 100).toFixed(1)) : 0,
                    }))} margin={{ top: 5, right: 10, bottom: 5, left: -18 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" />
                      <XAxis dataKey="size" tick={{ fontSize: 10 }} stroke="#94a3b8" />
                      <YAxis domain={[0, 100]} tick={{ fontSize: 10 }} stroke="#94a3b8" />
                      <Tooltip contentStyle={{ fontSize: 11, borderRadius: 10 }} />
                      <Legend wrapperStyle={{ fontSize: 11 }} />
                      <Bar dataKey="Recall" fill="#2563eb" radius={[4, 4, 0, 0]} />
                      <Bar dataKey="Precision" fill="#059669" radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : (
                <div className="h-64 flex items-center justify-center text-xs text-slate-400">
                  Run experiments at different leak sizes to map the detection floor.
                </div>
              )}
              {summary && summary.sensitivity.length === 1 && (
                <p className="text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-3 flex items-start space-x-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 shrink-0 mt-0.5" />
                  <span>Only one leak size has been tested. Run more sizes to establish a real detection floor.</span>
                </p>
              )}
            </div>
          </div>

          {/* Per-method comparison */}
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 mb-1">Per-Detector Comparison</h3>
            <p className="text-[11px] text-slate-400 mb-4">
              Each detector scored in isolation, so the fusion ensemble can be compared against its own inputs.
            </p>
            <div className="overflow-x-auto -mx-6 px-6">
              <table className="w-full text-xs min-w-[680px]">
                <thead>
                  <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-200">
                    <th className="py-2.5 pr-4 font-extrabold">Algorithm Method</th>
                    <th className="py-2.5 pr-4 font-extrabold">Precision</th>
                    <th className="py-2.5 pr-4 font-extrabold">Recall</th>
                    <th className="py-2.5 pr-4 font-extrabold">Median Latency</th>
                    <th className="py-2.5 font-extrabold">False Positives</th>
                  </tr>
                </thead>
                <tbody>
                  {(summary?.per_method ?? []).map((m) => {
                    const isFusion = m.key === "fusion";
                    return (
                      <tr key={m.key} className={`border-b border-slate-100 ${isFusion ? "bg-blue-50/50" : ""}`}>
                        <td className={`py-3 pr-4 ${isFusion ? "font-extrabold text-blue-700" : "font-bold text-slate-800"}`}>
                          {m.method}
                        </td>
                        <td className="py-3 pr-4 font-mono text-emerald-600 font-bold">{pct(m.precision)}</td>
                        <td className="py-3 pr-4 font-mono text-blue-600 font-bold">{pct(m.recall)}</td>
                        <td className="py-3 pr-4 font-mono text-amber-600 font-bold">{secs(m.median_latency_sec)}</td>
                        <td className={`py-3 font-mono font-bold ${m.false_positives > 10 ? "text-rose-600" : "text-slate-600"}`}>
                          {m.false_positives}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[11px] text-slate-500 mt-4 leading-relaxed">
              This table is the argument for multi-sensor fusion: individual detectors trade recall against
              false alarms, while the weighted ensemble keeps the recall of the most sensitive method without
              inheriting its false positives.
            </p>
          </div>
        </>
      )}
    </div>
  );
};

const TONES: Record<string, string> = {
  emerald: "text-emerald-600 bg-emerald-50 border-emerald-100",
  blue: "text-blue-600 bg-blue-50 border-blue-100",
  cyan: "text-cyan-600 bg-cyan-50 border-cyan-100",
  amber: "text-amber-600 bg-amber-50 border-amber-100",
};

const Metric: React.FC<{ label: string; value: string; sub: string; tone: string; icon: React.ReactNode }> = ({
  label, value, sub, tone, icon,
}) => (
  <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
    <div className="flex items-start justify-between">
      <div className="min-w-0">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</h3>
        <p className={`text-3xl font-extrabold mt-1.5 tracking-tight ${TONES[tone].split(" ")[0]}`}>{value}</p>
        <p className="text-[11px] text-slate-400 font-medium mt-1">{sub}</p>
      </div>
      <div className={`w-11 h-11 rounded-2xl border flex items-center justify-center shrink-0 ${TONES[tone]}`}>{icon}</div>
    </div>
  </div>
);
