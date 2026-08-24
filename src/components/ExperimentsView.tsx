import React, { useCallback, useEffect, useState } from "react";
import {
  ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend, ReferenceArea
} from "recharts";
import { Play, Square, FlaskConical, Tag, CheckCircle2, Loader2, AlertTriangle, Clock } from "lucide-react";
import type { ReplayRun } from "../types";
import { formatTimestamp, formatDuration } from "../lib/impact";

interface GroundTruthEvent {
  start_ts: number; stop_ts: number | null; location_node: string;
  severity_lpm: number; is_ground_truth: boolean; notes: string;
}
interface ExperimentStatus {
  run_active: boolean;
  run: { run_id: string; operator: string; location: string; leak_size_lpm: number;
         pump_mode: string; notes: string; start_ts: number; elapsed_sec: number; status: string } | null;
  leak_open: boolean;
  leak_event: { start_ts: number; elapsed_sec: number; location_node: string; severity_lpm: number } | null;
  ground_truth_events: GroundTruthEvent[];
}

/**
 * Experiment Control — digital ground-truth logging.
 *
 * Every control here writes to MongoDB through /api/experiments/*. Starting a
 * run stamps its run_id onto incoming live telemetry, and the ground-truth
 * buttons record machine timestamps at the moment the operator acts — which is
 * what turns detection latency into a measurement instead of a recollection.
 */
export const ExperimentsView: React.FC = () => {
  const [status, setStatus] = useState<ExperimentStatus | null>(null);
  const [runs, setRuns] = useState<ReplayRun[]>([]);
  const [selectedRun, setSelectedRun] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ kind: "ok" | "err"; text: string } | null>(null);

  // New-run form
  const [runId, setRunId] = useState("");
  const [operator, setOperator] = useState("");
  const [location, setLocation] = useState("Branch_A");
  const [leakSize, setLeakSize] = useState(0.5);
  const [notes, setNotes] = useState("");

  const refresh = useCallback(() => {
    fetch("/api/experiments/status").then((r) => r.json()).then(setStatus).catch(() => undefined);
    fetch("/api/benchmark/runs").then((r) => r.json()).then((d) => {
      const rows: ReplayRun[] = Array.isArray(d) ? d : [];
      setRuns(rows);
      setSelectedRun((cur) => cur ?? rows[0]?.run_id ?? null);
    }).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [refresh]);

  const post = (url: string, body?: any) => {
    setBusy(true);
    return fetch(url, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body ?? {}),
    })
      .then((r) => r.json())
      .then((d) => {
        if (d?.error) setMessage({ kind: "err", text: d.error });
        else setMessage({ kind: "ok", text: describe(url, d) });
        refresh();
        return d;
      })
      .catch(() => setMessage({ kind: "err", text: "Backend unreachable." }))
      .finally(() => setBusy(false));
  };

  const describe = (url: string, d: any) => {
    if (url.endsWith("/start") && d.run_id) return `Run ${d.run_id} started — live telemetry is now being tagged with this run.`;
    if (url.endsWith("/stop") && d.run_id) return `Run ${d.run_id} completed after ${d.duration_sec}s.`;
    if (url.includes("ground-truth/start")) return `Ground truth recorded: leak OPENED at ${formatTimestamp(d.start_ts)}.`;
    if (url.includes("ground-truth/stop")) return `Ground truth recorded: leak CLOSED after ${d.duration_sec}s.`;
    return "Done.";
  };

  const meta = runs.find((r) => r.run_id === selectedRun);
  const active = status?.run_active ? status.run : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
          <FlaskConical className="w-6 h-6 text-blue-600" />
          <span>Ground Truth Experiments & Benchmark Logging</span>
        </h2>
        <p className="text-xs text-slate-500 mt-1 max-w-3xl">
          Records what actually happened, with machine timestamps, straight to MongoDB
          (<code className="font-mono">experiment_runs</code> and <code className="font-mono">leak_events</code>).
          Detection accuracy is scored against these records — not against the detector's own output.
        </p>
        {message && (
          <p className={`mt-3 text-xs font-medium rounded-xl px-3.5 py-2.5 border ${
            message.kind === "ok"
              ? "text-emerald-700 bg-emerald-50 border-emerald-200"
              : "text-rose-700 bg-rose-50 border-rose-200"
          }`}>
            {message.text}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* Run control */}
        <div className="xl:col-span-5 bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
          <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center space-x-2">
            <Tag className="w-4 h-4 text-slate-500" />
            <span>{active ? "Active Run" : "Start a New Run"}</span>
          </h3>

          {active ? (
            <div className="space-y-3">
              <Row label="Run ID" value={active.run_id} mono />
              <Row label="Operator" value={active.operator} />
              <Row label="Leak Location" value={active.location} />
              <Row label="Target Leak Size" value={`${active.leak_size_lpm} L/min`} />
              <Row label="Started" value={formatTimestamp(active.start_ts)} />
              <Row label="Elapsed" value={formatDuration(active.elapsed_sec)} />
              {active.notes && <Row label="Notes" value={active.notes} />}

              <button
                onClick={() => post("/api/experiments/stop")}
                disabled={busy}
                className="w-full mt-2 px-4 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white text-xs font-bold rounded-xl flex items-center justify-center space-x-2 transition"
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Square className="w-4 h-4" />}
                <span>Stop Run</span>
              </button>
            </div>
          ) : (
            <div className="space-y-3.5">
              <Field label="Run ID (blank = auto)">
                <input value={runId} onChange={(e) => setRunId(e.target.value)}
                       placeholder="RUN_20260810_1400" className={inputClass} />
              </Field>
              <Field label="Operator">
                <input value={operator} onChange={(e) => setOperator(e.target.value)}
                       placeholder="your name" className={inputClass} />
              </Field>
              <div className="grid grid-cols-2 gap-3">
                <Field label="Leak Location">
                  <select value={location} onChange={(e) => setLocation(e.target.value)} className={inputClass}>
                    <option>Branch_A</option><option>Branch_B</option><option>Main_Trunk</option>
                  </select>
                </Field>
                <Field label="Calibrated Leak (L/min)">
                  <input type="number" step={0.05} min={0} value={leakSize}
                         onChange={(e) => setLeakSize(Number(e.target.value))} className={inputClass} />
                </Field>
              </div>
              <Field label="Notes">
                <input value={notes} onChange={(e) => setNotes(e.target.value)}
                       placeholder="e.g. micro-leak sensitivity baseline" className={inputClass} />
              </Field>

              <button
                onClick={() => post("/api/experiments/start", {
                  run_id: runId.trim() || undefined, operator: operator.trim() || "unknown",
                  location, leak_size_lpm: leakSize, notes: notes.trim(),
                })}
                disabled={busy}
                className="w-full px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-bold rounded-xl flex items-center justify-center space-x-2 transition"
              >
                {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
                <span>Start Run</span>
              </button>
              <p className="text-[11px] text-slate-400 leading-relaxed">
                Starting a run tags incoming live telemetry with its ID so the session can be scored later.
                On Test Bench the generated stream is tagged with the run, so both ground truth and telemetry are recorded.
              </p>
            </div>
          )}
        </div>

        {/* Ground truth logger */}
        <div className="xl:col-span-7 bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-900">Digital Ground Truth Logger</h3>
            <span className={`px-2.5 py-1 rounded-lg text-[10px] font-extrabold border ${
              !active ? "bg-slate-100 text-slate-500 border-slate-200"
                : status?.leak_open ? "bg-rose-100 text-rose-700 border-rose-200 animate-pulse"
                : "bg-emerald-100 text-emerald-700 border-emerald-200"
            }`}>
              {!active ? "NO ACTIVE RUN" : status?.leak_open ? "LEAK OPEN" : "READY"}
            </span>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            {status?.leak_open ? (
              <button
                onClick={() => post("/api/experiments/ground-truth/stop")}
                disabled={busy}
                className="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white text-xs font-bold rounded-xl flex items-center space-x-2 transition"
              >
                <Square className="w-4 h-4" />
                <span>Stop Ground Truth Leak Event</span>
              </button>
            ) : (
              <button
                onClick={() => post("/api/experiments/ground-truth/start")}
                disabled={busy || !active}
                className="px-4 py-2.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-40 disabled:cursor-not-allowed text-white text-xs font-bold rounded-xl flex items-center space-x-2 transition"
              >
                <Play className="w-4 h-4" />
                <span>Start Ground Truth Leak Event</span>
              </button>
            )}
            {status?.leak_open && status.leak_event && (
              <span className="text-xs font-bold text-rose-600 flex items-center space-x-1.5">
                <Clock className="w-3.5 h-3.5" />
                <span>open for {formatDuration(status.leak_event.elapsed_sec)}</span>
              </span>
            )}
          </div>

          <p className="text-[11px] text-slate-400 mt-3 leading-relaxed">
            Press at the same instant you turn the valve. Hold the leak for a{" "}
            <strong className="text-slate-600">predetermined duration</strong> — closing it because the
            system detected would make recall 100% by construction and measure nothing.
          </p>

          {/* Recorded events */}
          <div className="mt-5 pt-5 border-t border-slate-100">
            <h4 className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-3">
              Recorded Ground Truth {active ? `— ${active.run_id}` : ""}
            </h4>
            {(status?.ground_truth_events?.length ?? 0) === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center border border-dashed border-slate-200 rounded-xl">
                {active ? "No leak events logged yet for this run." : "Start a run to begin logging."}
              </p>
            ) : (
              <div className="space-y-2">
                {status!.ground_truth_events.map((e, i) => (
                  <div key={i} className="flex items-center justify-between text-xs bg-slate-50 border border-slate-200/70 rounded-xl px-3.5 py-2.5">
                    <div className="flex items-center space-x-2.5 min-w-0">
                      <CheckCircle2 className={`w-4 h-4 shrink-0 ${e.stop_ts ? "text-emerald-600" : "text-amber-500"}`} />
                      <div className="min-w-0">
                        <div className="font-bold text-slate-800">
                          {e.location_node} · {e.severity_lpm} L/min
                        </div>
                        <div className="text-[11px] text-slate-400">
                          {formatTimestamp(e.start_ts)} → {e.stop_ts ? formatTimestamp(e.stop_ts) : "open"}
                        </div>
                      </div>
                    </div>
                    <span className="font-mono font-bold text-slate-600 shrink-0">
                      {e.stop_ts ? formatDuration(e.stop_ts - e.start_ts) : "—"}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Stored runs */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 mb-4">Stored Runs</h3>
        {runs.length === 0 ? (
          <p className="text-xs text-slate-400 py-8 text-center border border-dashed border-slate-200 rounded-xl">
            No runs recorded yet. Start one above, or score a scenario from Mock Scenarios.
          </p>
        ) : (
          <>
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-3">
              {runs.map((r) => (
                <button
                  key={r.run_id}
                  onClick={() => setSelectedRun(r.run_id)}
                  className={`text-left rounded-2xl border p-4 transition ${
                    selectedRun === r.run_id
                      ? "border-blue-400 bg-blue-50/60 shadow-2xs"
                      : "border-slate-200 bg-white hover:border-blue-200"
                  }`}
                >
                  <div className="text-sm font-extrabold text-slate-800 font-mono truncate">{r.run_id}</div>
                  <div className="text-[11px] text-slate-500 mt-1">{r.date} · {r.operator}</div>
                  <div className="text-[11px] text-slate-400">{r.location} · {r.leak_size_lpm} L/min</div>
                </button>
              ))}
            </div>

            {meta && (
              <div className="mt-5 pt-5 border-t border-slate-100 grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
                <Row label="Operator" value={meta.operator} />
                <Row label="Location" value={meta.location} />
                <Row label="Calibrated Leak" value={`${meta.leak_size_lpm} L/min`} />
                <Row label="Duration" value={meta.duration_sec ? `${meta.duration_sec}s` : "—"} />
              </div>
            )}
          </>
        )}
      </div>

      <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4 flex items-start space-x-2.5">
        <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
        <p className="text-xs text-amber-800 leading-relaxed">
          Run clean sessions too — with the valve never opened. Without them there is nothing to
          measure false alarms against, and precision cannot be established.
        </p>
      </div>
    </div>
  );
};

const inputClass =
  "w-full px-3 py-2.5 border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 bg-white focus:outline-hidden focus:ring-2 focus:ring-blue-500/40";

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-1.5">{label}</label>
    {children}
  </div>
);

const Row: React.FC<{ label: string; value: string; mono?: boolean }> = ({ label, value, mono }) => (
  <div className="flex items-center justify-between bg-slate-50 border border-slate-200/70 rounded-xl px-3.5 py-2.5">
    <span className="text-[11px] font-semibold text-slate-500">{label}</span>
    <span className={`text-xs font-bold text-slate-800 ${mono ? "font-mono" : ""}`}>{value}</span>
  </div>
);
