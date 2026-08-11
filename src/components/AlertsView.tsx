import React, { useCallback, useEffect, useState } from "react";
import {
  Bell, AlertTriangle, CheckCircle2, XCircle, RotateCcw, MapPin, Clock,
  Droplets, IndianRupee, ClipboardList, ShieldAlert, Loader2
} from "lucide-react";
import type { AlertsSummary, LeakAlert, SavingsSummary } from "../types";
import {
  formatDuration, formatLitres, formatMoney, formatRate, formatTimestamp,
  severityStyle, statusStyle, urgencyStyle,
} from "../lib/impact";

type StatusFilter = "ALL" | "ACTIVE" | "RESOLVED" | "FALSE_POSITIVE";

const TABS: { id: StatusFilter; label: string; countKey: keyof AlertsSummary["counts"] | null }[] = [
  { id: "ACTIVE", label: "Active", countKey: "active" },
  { id: "RESOLVED", label: "Resolved", countKey: "resolved" },
  { id: "FALSE_POSITIVE", label: "False Alerts", countKey: "false_positive" },
  { id: "ALL", label: "All", countKey: "total" },
];

/**
 * Alert Center — the operator's incident queue.
 *
 * Every row is a real detection incident aggregated by backend/alerts from the
 * mock or live pipeline, with its quantified impact attached. Dispositioning
 * an alert here is what feeds the Water Savings counter.
 */
export const AlertsView: React.FC<{ readOnly?: boolean }> = ({ readOnly = false }) => {
  const [tab, setTab] = useState<StatusFilter>("ACTIVE");
  const [alerts, setAlerts] = useState<LeakAlert[]>([]);
  const [summary, setSummary] = useState<AlertsSummary | null>(null);
  const [savings, setSavings] = useState<SavingsSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback((status: StatusFilter) => {
    const query = status === "ALL" ? "" : `?status=${status}`;
    Promise.all([
      fetch(`/api/alerts${query}`).then((r) => r.json()),
      fetch("/api/alerts/summary").then((r) => r.json()),
      fetch("/api/savings").then((r) => r.json()),
    ])
      .then(([rows, sum, sav]) => {
        setAlerts(Array.isArray(rows) ? rows : []);
        setSummary(sum);
        setSavings(sav);
        setError(null);
      })
      .catch(() => setError("Could not reach the alert service."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    setLoading(true);
    load(tab);
    // Poll so incidents raised by the running pipeline appear without a manual refresh.
    const interval = setInterval(() => load(tab), 5000);
    return () => clearInterval(interval);
  }, [tab, load]);

  const act = (alertId: string, action: "resolve" | "false-positive" | "reopen") => {
    setBusyId(alertId);
    fetch(`/api/alerts/${alertId}/${action}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data?.savings) setSavings(data.savings);
        load(tab);
      })
      .catch(() => setError(`Could not update ${alertId}.`))
      .finally(() => setBusyId(null));
  };

  const counts = summary?.counts;

  return (
    <div className="space-y-6">
      {/* KPI strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-5">
        <KpiCard label="Active Incidents" value={counts?.active ?? 0} tone="rose" icon={<AlertTriangle className="w-5 h-5" />} sub={`${counts?.open_now ?? 0} still in alarm`} />
        <KpiCard label="Repaired" value={counts?.resolved ?? 0} tone="emerald" icon={<CheckCircle2 className="w-5 h-5" />} sub={formatLitres(savings?.water_saved_litres, { compact: true }) + " saved"} />
        <KpiCard label="False Alerts" value={counts?.false_positive ?? 0} tone="slate" icon={<XCircle className="w-5 h-5" />} sub={savings?.detection_precision !== null && savings?.detection_precision !== undefined ? `${(savings.detection_precision * 100).toFixed(0)}% precision` : "no dispositions yet"} />
        <KpiCard label="Money Saved" value={formatMoney(savings?.money_saved, savings?.currency_symbol ?? "₹", { compact: true })} tone="blue" icon={<IndianRupee className="w-5 h-5" />} sub={`over ${savings?.horizon_days ?? 30} days each`} />
      </div>

      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
              <Bell className="w-6 h-6 text-blue-600" />
              <span>Alert Center</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1 max-w-2xl">
              Leak incidents raised by the detection pipeline, with quantified water and cost impact.
              {readOnly
                ? "This judge-facing view is read-only; incident disposition remains with the local operator."
                : "Dispositioning an incident feeds the water-savings KPI."}
            </p>
          </div>

          <div className="flex items-center space-x-1 bg-slate-100 p-1 rounded-xl text-xs font-semibold">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`px-3 py-1.5 rounded-lg transition flex items-center space-x-1.5 ${
                  tab === t.id ? "bg-white text-slate-900 shadow-2xs font-bold" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                <span>{t.label}</span>
                {t.countKey && counts && (
                  <span className={`px-1.5 rounded-md text-[10px] font-extrabold ${tab === t.id ? "bg-slate-200 text-slate-700" : "bg-slate-200/70 text-slate-500"}`}>
                    {counts[t.countKey]}
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {error && (
          <p className="mb-4 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-2.5 font-medium">{error}</p>
        )}

        {loading && alerts.length === 0 ? (
          <div className="py-16 text-center text-slate-400 text-sm flex items-center justify-center space-x-2">
            <Loader2 className="w-4 h-4 animate-spin" /><span>Loading incidents…</span>
          </div>
        ) : alerts.length === 0 ? (
          <div className="py-16 text-center">
            <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto mb-3" />
            <p className="text-sm font-bold text-slate-600">No {tab === "ALL" ? "" : statusStyle(tab).label.toLowerCase()} incidents</p>
            <p className="text-xs text-slate-400 mt-1">
              Incidents appear here automatically when the detection pipeline confirms a leak.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {alerts.map((a) => (
              <AlertRow key={a.alert_id} alert={a} busy={busyId === a.alert_id} onAct={act} readOnly={readOnly} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

const KPI_TONES: Record<string, string> = {
  rose: "bg-rose-50 border-rose-100 text-rose-600",
  emerald: "bg-emerald-50 border-emerald-100 text-emerald-600",
  slate: "bg-slate-100 border-slate-200 text-slate-600",
  blue: "bg-blue-50 border-blue-100 text-blue-600",
};

const KpiCard: React.FC<{ label: string; value: React.ReactNode; tone: string; icon: React.ReactNode; sub: string }> = ({
  label, value, tone, icon, sub,
}) => (
  <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs flex items-start justify-between">
    <div className="min-w-0">
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</h3>
      <p className="text-2xl font-extrabold text-slate-900 mt-1 tracking-tight">{value}</p>
      <p className="text-xs text-slate-400 font-medium mt-0.5">{sub}</p>
    </div>
    <div className={`w-11 h-11 rounded-2xl border flex items-center justify-center shrink-0 ${KPI_TONES[tone]}`}>{icon}</div>
  </div>
);

const AlertRow: React.FC<{
  alert: LeakAlert;
  busy: boolean;
  onAct: (id: string, action: "resolve" | "false-positive" | "reopen") => void;
  readOnly?: boolean;
}> = ({ alert, busy, onAct, readOnly = false }) => {
  const sev = severityStyle(alert.impact?.severity);
  const st = statusStyle(alert.status);
  const urg = urgencyStyle(alert.impact?.urgency);
  const symbol = alert.impact?.currency_symbol ?? "₹";
  const fpRate = alert.false_positive_warning?.estimated_false_positive_rate;
  // null now, always, until runs are scored against logged leak events. The old
  // per-tier table (1/3/8/20%) was never measured — see _FP_RATE_BASIS in
  // backend/response/response_builder.py.
  const fpBasis = alert.false_positive_warning?.basis;

  return (
    <div className={`border rounded-2xl p-5 transition ${alert.status === "ACTIVE" ? "bg-white border-slate-200" : "bg-slate-50/70 border-slate-200/70"}`}>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="flex items-start space-x-3.5 min-w-0 flex-1">
          <div className={`w-10 h-10 rounded-xl flex items-center justify-center shrink-0 border ${sev.badge}`}>
            <AlertTriangle className="w-5 h-5" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="text-sm font-bold text-slate-800">
                {alert.alert_id} · Leak suspected in {alert.zone}
              </h4>
              <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold border ${sev.badge}`}>
                {sev.emoji} {alert.impact?.severity ?? "—"}
              </span>
              <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold border ${st.badge}`}>{st.label}</span>
              {alert.is_open && (
                <span className="px-2 py-0.5 rounded-md text-[10px] font-extrabold bg-rose-600 text-white animate-pulse">IN ALARM</span>
              )}
            </div>

            <p className="text-xs text-slate-500 mt-1.5 leading-relaxed">{alert.evidence}</p>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] text-slate-400 font-medium mt-2">
              <span className="flex items-center space-x-1"><Clock className="w-3.5 h-3.5" /><span>{formatTimestamp(alert.start_ts)}</span></span>
              <span className="flex items-center space-x-1"><MapPin className="w-3.5 h-3.5" /><span>{alert.zone}</span></span>
              <span>Duration {formatDuration(alert.duration_sec)}</span>
              <span>Likelihood {Number(alert.likelihood_score ?? 0).toFixed(1)}%</span>
              <span>Confidence {alert.confidence_tier}</span>
              {alert.active_methods?.length > 0 && <span>Confirmed by {alert.active_methods.join(", ")}</span>}
            </div>

            {alert.resolution_note && (
              <p className="text-[11px] text-slate-500 mt-2 italic bg-white border border-slate-200 rounded-lg px-2.5 py-1.5">
                {alert.resolution_note}
              </p>
            )}
          </div>
        </div>

        {/* Actions */}
        {!readOnly && <div className="flex items-center space-x-2 shrink-0">
          {alert.status === "ACTIVE" ? (
            <>
              <button
                disabled={busy}
                onClick={() => onAct(alert.alert_id, "resolve")}
                className="px-3 py-2 bg-emerald-600 hover:bg-emerald-700 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center space-x-1.5 transition"
              >
                {busy ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                <span>Mark Repaired</span>
              </button>
              <button
                disabled={busy}
                onClick={() => onAct(alert.alert_id, "false-positive")}
                className="px-3 py-2 bg-white border border-slate-200 hover:border-slate-300 text-slate-600 disabled:opacity-50 text-xs font-bold rounded-xl flex items-center space-x-1.5 transition"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>False Alert</span>
              </button>
            </>
          ) : (
            <button
              disabled={busy}
              onClick={() => onAct(alert.alert_id, "reopen")}
              className="px-3 py-2 bg-white border border-slate-200 hover:border-blue-300 hover:text-blue-600 text-slate-600 disabled:opacity-50 text-xs font-bold rounded-xl flex items-center space-x-1.5 transition"
            >
              <RotateCcw className="w-3.5 h-3.5" />
              <span>Reopen</span>
            </button>
          )}
        </div>}
      </div>

      {/* Impact strip */}
      <div className="mt-4 pt-4 border-t border-slate-100 grid grid-cols-2 md:grid-cols-4 gap-4">
        <MiniStat icon={<Droplets className="w-3.5 h-3.5" />} label="Peak Rate" value={formatRate(alert.peak_leak_rate_lpm)} />
        <MiniStat icon={<Droplets className="w-3.5 h-3.5" />} label="Loss / Day" value={formatLitres(alert.impact?.litres_per_day, { compact: true })} />
        <MiniStat icon={<IndianRupee className="w-3.5 h-3.5" />} label="Cost / Year" value={formatMoney(alert.impact?.cost_per_year, symbol, { compact: true })} />
        {alert.status === "RESOLVED" ? (
          <MiniStat icon={<CheckCircle2 className="w-3.5 h-3.5" />} label="Water Saved" value={formatLitres(alert.water_saved_litres, { compact: true })} tone="text-emerald-600" />
        ) : (
          <MiniStat icon={<ShieldAlert className="w-3.5 h-3.5" />} label="Urgency" value={alert.impact?.urgency ?? "—"} tone={urg.text} />
        )}
      </div>

      {/* Work order + false-positive warning */}
      {(alert.work_order_summary || fpBasis) && (
        <div className="mt-4 space-y-2.5">
          {alert.work_order_summary?.summary && (
            <div className="bg-blue-50/60 border border-blue-100 rounded-xl px-3.5 py-3">
              <p className="text-[10px] font-extrabold text-blue-700 uppercase tracking-wider flex items-center justify-between mb-1">
                <span className="flex items-center space-x-1.5">
                  <ClipboardList className="w-3.5 h-3.5" /><span>Work Order Summary</span>
                </span>
                <span className="text-slate-400 font-bold normal-case tracking-normal">
                  {alert.work_order_summary.source === "llm" ? "Azure OpenAI" : "template"}
                </span>
              </p>
              <p className="text-xs text-slate-600 leading-relaxed whitespace-pre-line">
                {alert.work_order_summary.summary}
              </p>
            </div>
          )}
          {fpBasis && (
            <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5 leading-relaxed">
              <strong>
                False-positive rate:{" "}
                {fpRate == null ? "not yet measured" : `${(fpRate * 100).toFixed(1)}%`}
              </strong>{" "}
              at {alert.confidence_tier} confidence. {fpBasis}
            </p>
          )}
        </div>
      )}
    </div>
  );
};

const MiniStat: React.FC<{ icon: React.ReactNode; label: string; value: string; tone?: string }> = ({
  icon, label, value, tone = "text-slate-900",
}) => (
  <div>
    <p className="text-[10px] font-bold text-slate-400 uppercase tracking-wider flex items-center space-x-1">
      {icon}<span>{label}</span>
    </p>
    <p className={`text-sm font-extrabold mt-0.5 ${tone}`}>{value}</p>
  </div>
);
