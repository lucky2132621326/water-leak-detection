import React, { useCallback, useEffect, useMemo, useState } from "react";
import { History, Search, Filter, RotateCcw, BarChart3, Droplets, TrendingUp } from "lucide-react";
import type { AlertsSummary, LeakAlert, SavingsSummary } from "../types";
import {
  formatDuration, formatLitres, formatMoney, formatRate, formatTimestamp,
  severityStyle, statusStyle,
} from "../lib/impact";

const SEVERITIES = ["ALL", "MINOR", "MODERATE", "MAJOR", "CRITICAL"];
const STATUSES = ["ALL", "ACTIVE", "RESOLVED", "FALSE_POSITIVE"];
const RANGES: { label: string; days: number | null }[] = [
  { label: "Last 7 Days", days: 7 },
  { label: "Last 30 Days", days: 30 },
  { label: "Last 90 Days", days: 90 },
  { label: "All Time", days: null },
];

/**
 * Leak History Explorer — the investigative view over past incidents.
 *
 * Filters are applied server-side by backend/alerts so the same query logic
 * backs the API and this screen; the monthly strip shows long-term monitoring
 * coverage rather than just the current queue.
 */
export const LeakHistoryView: React.FC = () => {
  const [alerts, setAlerts] = useState<LeakAlert[]>([]);
  const [summary, setSummary] = useState<AlertsSummary | null>(null);
  const [savings, setSavings] = useState<SavingsSummary | null>(null);
  const [loading, setLoading] = useState(true);

  const [status, setStatus] = useState("ALL");
  const [zone, setZone] = useState("ALL");
  const [severity, setSeverity] = useState("ALL");
  const [minConfidence, setMinConfidence] = useState(0);
  const [rangeDays, setRangeDays] = useState<number | null>(30);
  const [search, setSearch] = useState("");

  const runQuery = useCallback(() => {
    const params = new URLSearchParams();
    if (status !== "ALL") params.set("status", status);
    if (zone !== "ALL") params.set("zone", zone);
    if (severity !== "ALL") params.set("severity", severity);
    if (minConfidence > 0) params.set("min_confidence", String(minConfidence));
    if (rangeDays !== null) params.set("since_ts", String(Math.floor(Date.now() / 1000) - rangeDays * 86400));
    if (search.trim()) params.set("search", search.trim());

    setLoading(true);
    fetch(`/api/alerts?${params.toString()}`)
      .then((r) => r.json())
      .then((rows) => setAlerts(Array.isArray(rows) ? rows : []))
      .catch(() => setAlerts([]))
      .finally(() => setLoading(false));
  }, [status, zone, severity, minConfidence, rangeDays, search]);

  useEffect(() => {
    const t = setTimeout(runQuery, 200);
    return () => clearTimeout(t);
  }, [runQuery]);

  useEffect(() => {
    fetch("/api/alerts/summary").then((r) => r.json()).then(setSummary).catch(() => setSummary(null));
    fetch("/api/savings").then((r) => r.json()).then(setSavings).catch(() => setSavings(null));
  }, []);

  const reset = () => {
    setStatus("ALL"); setZone("ALL"); setSeverity("ALL");
    setMinConfidence(0); setRangeDays(30); setSearch("");
  };

  const totals = useMemo(() => {
    const litres = alerts.reduce((sum, a) => sum + (a.impact?.litres_per_day ?? 0), 0);
    const cost = alerts.reduce((sum, a) => sum + (a.impact?.cost_per_year ?? 0), 0);
    const peak = alerts.reduce((m, a) => Math.max(m, a.peak_leak_rate_lpm ?? 0), 0);
    return { litres, cost, peak };
  }, [alerts]);

  const maxBucket = Math.max(1, ...(summary?.timeline ?? []).map((b) => b.total));
  const zones = ["ALL", ...(summary?.zones ?? [])];

  return (
    <div className="space-y-6">
      {/* Monthly trend */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-5">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
              <History className="w-6 h-6 text-blue-600" />
              <span>Leak History Explorer</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1 max-w-2xl">
              Investigate past incidents across zones, severities and time. Demonstrates continuous
              monitoring coverage, not just point-in-time detection.
            </p>
          </div>
          <div className="flex items-center space-x-5 text-right">
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Incidents Logged</p>
              <p className="text-xl font-extrabold text-slate-900">{summary?.counts.total ?? 0}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Water Recovered</p>
              <p className="text-xl font-extrabold text-emerald-600">{formatLitres(savings?.water_saved_litres, { compact: true })}</p>
            </div>
          </div>
        </div>

        {(summary?.timeline?.length ?? 0) > 0 ? (
          <div className="flex items-end space-x-3 h-32 border-b border-slate-200 pb-0.5">
            {summary!.timeline.map((b) => (
              <div key={b.month} className="flex-1 max-w-[88px] flex flex-col items-center justify-end h-full group">
                <span className="text-[10px] font-extrabold text-slate-600 mb-1">{b.total}</span>
                <div className="w-full flex flex-col justify-end rounded-t-lg overflow-hidden" style={{ height: `${(b.total / maxBucket) * 100}%` }}>
                  {b.active > 0 && <div className="bg-rose-500 w-full" style={{ flexGrow: b.active }} title={`${b.active} active`} />}
                  {b.false_positive > 0 && <div className="bg-slate-400 w-full" style={{ flexGrow: b.false_positive }} title={`${b.false_positive} false alerts`} />}
                  {b.resolved > 0 && <div className="bg-emerald-500 w-full" style={{ flexGrow: b.resolved }} title={`${b.resolved} resolved`} />}
                </div>
                <span className="text-[10px] text-slate-400 font-semibold mt-1.5 whitespace-nowrap">{b.month}</span>
              </div>
            ))}
          </div>
        ) : (
          <div className="h-32 flex items-center justify-center text-xs text-slate-400 border border-dashed border-slate-200 rounded-xl">
            <BarChart3 className="w-4 h-4 mr-2" /> No incident history recorded yet
          </div>
        )}

        <div className="flex items-center space-x-4 mt-4 text-[11px] font-semibold text-slate-500">
          <span className="flex items-center space-x-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-rose-500" /><span>Active</span></span>
          <span className="flex items-center space-x-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-emerald-500" /><span>Resolved</span></span>
          <span className="flex items-center space-x-1.5"><span className="w-2.5 h-2.5 rounded-sm bg-slate-400" /><span>False Alert</span></span>
        </div>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex items-center justify-between mb-5">
          <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <Filter className="w-4 h-4 text-slate-500" /><span>Filters</span>
          </h3>
          <button onClick={reset} className="text-xs font-bold text-slate-500 hover:text-blue-600 flex items-center space-x-1.5 transition">
            <RotateCcw className="w-3.5 h-3.5" /><span>Reset</span>
          </button>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          <Field label="Status">
            <select value={status} onChange={(e) => setStatus(e.target.value)} className={selectClass}>
              {STATUSES.map((s) => <option key={s} value={s}>{s === "ALL" ? "All statuses" : statusStyle(s).label}</option>)}
            </select>
          </Field>

          <Field label="Zone / Branch">
            <select value={zone} onChange={(e) => setZone(e.target.value)} className={selectClass}>
              {zones.map((z) => <option key={z} value={z}>{z === "ALL" ? "All zones" : z}</option>)}
            </select>
          </Field>

          <Field label="Severity">
            <select value={severity} onChange={(e) => setSeverity(e.target.value)} className={selectClass}>
              {SEVERITIES.map((s) => <option key={s} value={s}>{s === "ALL" ? "All severities" : s}</option>)}
            </select>
          </Field>

          <Field label="Date Range">
            <select
              value={String(rangeDays)}
              onChange={(e) => setRangeDays(e.target.value === "null" ? null : Number(e.target.value))}
              className={selectClass}
            >
              {RANGES.map((r) => <option key={r.label} value={String(r.days)}>{r.label}</option>)}
            </select>
          </Field>

          <Field label={`Min. Likelihood — ${minConfidence}%`}>
            <input
              type="range" min={0} max={100} step={5}
              value={minConfidence}
              onChange={(e) => setMinConfidence(Number(e.target.value))}
              className="w-full accent-blue-600 cursor-pointer mt-2.5"
            />
          </Field>

          <Field label="Search">
            <div className="relative">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text" value={search} onChange={(e) => setSearch(e.target.value)}
                placeholder="Alert ID, zone, evidence…"
                className={`${selectClass} pl-9`}
              />
            </div>
          </Field>
        </div>
      </div>

      {/* Results */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-4 mb-5">
          <h3 className="text-sm font-bold text-slate-900">
            {loading ? "Searching…" : `${alerts.length} incident${alerts.length === 1 ? "" : "s"} matched`}
          </h3>
          {alerts.length > 0 && (
            <div className="flex items-center space-x-5 text-xs">
              <span className="flex items-center space-x-1.5 text-slate-500 font-semibold">
                <Droplets className="w-3.5 h-3.5" /><span>Peak {formatRate(totals.peak)}</span>
              </span>
              <span className="flex items-center space-x-1.5 text-slate-500 font-semibold">
                <TrendingUp className="w-3.5 h-3.5" /><span>Combined {formatMoney(totals.cost, savings?.currency_symbol ?? "₹", { compact: true })}/yr exposure</span>
              </span>
            </div>
          )}
        </div>

        {alerts.length === 0 && !loading ? (
          <div className="py-14 text-center">
            <Search className="w-9 h-9 text-slate-300 mx-auto mb-3" />
            <p className="text-sm font-bold text-slate-500">No incidents match these filters</p>
            <p className="text-xs text-slate-400 mt-1">Try widening the date range or clearing the severity filter.</p>
          </div>
        ) : (
          <div className="overflow-x-auto -mx-6 px-6">
            <table className="w-full text-xs min-w-[900px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-slate-400 border-b border-slate-200">
                  <th className="py-2.5 pr-4 font-extrabold">Alert</th>
                  <th className="py-2.5 pr-4 font-extrabold">Detected</th>
                  <th className="py-2.5 pr-4 font-extrabold">Zone</th>
                  <th className="py-2.5 pr-4 font-extrabold">Peak Rate</th>
                  <th className="py-2.5 pr-4 font-extrabold">Severity</th>
                  <th className="py-2.5 pr-4 font-extrabold">Likelihood</th>
                  <th className="py-2.5 pr-4 font-extrabold">Duration</th>
                  <th className="py-2.5 pr-4 font-extrabold">Annual Cost</th>
                  <th className="py-2.5 font-extrabold">Status</th>
                </tr>
              </thead>
              <tbody>
                {alerts.map((a) => {
                  const sev = severityStyle(a.impact?.severity);
                  const st = statusStyle(a.status);
                  return (
                    <tr key={a.alert_id} className="border-b border-slate-100 hover:bg-slate-50/70 transition">
                      <td className="py-3 pr-4 font-bold text-slate-800 whitespace-nowrap">{a.alert_id}</td>
                      <td className="py-3 pr-4 text-slate-500 whitespace-nowrap">{formatTimestamp(a.start_ts)}</td>
                      <td className="py-3 pr-4 text-slate-600 font-semibold whitespace-nowrap">{a.zone}</td>
                      <td className="py-3 pr-4 font-mono text-slate-800 whitespace-nowrap">{formatRate(a.peak_leak_rate_lpm)}</td>
                      <td className="py-3 pr-4">
                        <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold border whitespace-nowrap ${sev.badge}`}>
                          {sev.emoji} {a.impact?.severity ?? "—"}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-slate-600 font-semibold whitespace-nowrap">{Number(a.likelihood_score ?? 0).toFixed(1)}%</td>
                      <td className="py-3 pr-4 text-slate-500 whitespace-nowrap">{formatDuration(a.duration_sec)}</td>
                      <td className="py-3 pr-4 font-bold text-rose-600 whitespace-nowrap">
                        {formatMoney(a.impact?.cost_per_year, a.impact?.currency_symbol ?? "₹", { compact: true })}
                      </td>
                      <td className="py-3">
                        <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold border whitespace-nowrap ${st.badge}`}>{st.label}</span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};

const selectClass =
  "w-full px-3 py-2.5 border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 bg-white focus:outline-hidden focus:ring-2 focus:ring-blue-500/40";

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1.5">{label}</label>
    {children}
  </div>
);
