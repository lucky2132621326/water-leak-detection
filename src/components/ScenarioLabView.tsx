import React, { useCallback, useEffect, useState } from "react";
import {
  FlaskConical, Play, Loader2, CheckCircle2, XCircle, AlertTriangle,
  Radio, Clock, Droplets, Info
} from "lucide-react";
import type { ModeState, ScenarioSummary, ScenarioRunResult } from "../types";

/**
 * Mock Scenarios.
 *
 * Two distinct actions, deliberately separated:
 *
 *   Stream  — feed the scenario into the dashboard live, so every view
 *             (detectors, alerts, impact) animates as it would with a real rig.
 *   Score   — run the whole scenario instantly and grade it against its own
 *             ground truth. This is the regression-test path.
 *
 * Both go through the same ingestion and detection pipeline as live sensors.
 */
export const ScenarioLabView: React.FC<{ onModeChange?: () => void }> = ({ onModeChange }) => {
  const [scenarios, setScenarios] = useState<ScenarioSummary[]>([]);
  const [mode, setMode] = useState<ModeState | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, ScenarioRunResult>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [runningAll, setRunningAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [custom, setCustom] = useState({ rate: 1.0, location: "Main_Trunk", ramp: 0, noise: 0.02, startTime: "" });

  const runCustom = () => {
    setBusy("__custom__");
    const duration = 300;
    fetch("/api/scenarios/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        run_id: "MOCK_custom",
        scenario: {
          id: "custom", name: "Custom Scenario",
          description: `${custom.rate} L/min on ${custom.location}` + (custom.ramp ? ` ramping over ${custom.ramp}s` : ""),
          duration_sec: duration,
          noise_sigma_lpm: custom.noise,
          start_time: custom.startTime.trim() || null,
          branch_flow_lpm: custom.location.startsWith("Branch") ? 0.6 : 0.0,
          expect_detection: custom.rate > 0,
          expect_zone: custom.rate > 0 ? custom.location : null,
          leaks: custom.rate > 0
            ? [{ start_sec: 100, end_sec: 240, rate_lpm: custom.rate, ramp_sec: custom.ramp, location: custom.location }]
            : [],
        },
      }),
    })
      .then((r) => r.json())
      .then((d: ScenarioRunResult) => {
        if (d.success) setResults((prev) => ({ ...prev, __custom__: d }));
        else setError((d as any).error ?? "Custom scenario failed.");
      })
      .catch(() => setError("Custom scenario failed."))
      .finally(() => setBusy(null));
  };

  const refresh = useCallback(() => {
    fetch("/api/scenarios").then((r) => r.json()).then((d) => {
      setScenarios(d.scenarios ?? []);
      setSelected((cur) => cur ?? d.active ?? d.scenarios?.[0]?.id ?? null);
    }).catch(() => setError("Could not load scenarios."));
    fetch("/api/mode").then((r) => r.json()).then(setMode).catch(() => undefined);
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(() => fetch("/api/mode").then((r) => r.json()).then(setMode).catch(() => undefined), 3000);
    return () => clearInterval(t);
  }, [refresh]);

  const stream = (scenarioId: string) => {
    setBusy(scenarioId);
    fetch("/api/mode", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode: "mock", scenario_id: scenarioId, speed: 8 }),
    })
      .then((r) => r.json())
      .then((d) => { if (!d.success) setError(d.error); refresh(); onModeChange?.(); })
      .catch(() => setError("Could not switch scenario."))
      .finally(() => setBusy(null));
  };

  const score = (scenarioId: string) => {
    setBusy(scenarioId);
    return fetch("/api/scenarios/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_id: scenarioId }),
    })
      .then((r) => r.json())
      .then((d: ScenarioRunResult) => {
        if (d.success) setResults((prev) => ({ ...prev, [scenarioId]: d }));
        else setError((d as any).error ?? "Scenario run failed.");
        return d;
      })
      .catch(() => setError("Scenario run failed."))
      .finally(() => setBusy(null));
  };

  const scoreAll = async () => {
    setRunningAll(true);
    setError(null);
    for (const s of scenarios) {
      // Sequential on purpose — each run replays a full scenario through the
      // pipeline, and running them concurrently would contend for the DB.
      // eslint-disable-next-line no-await-in-loop
      await score(s.id);
    }
    setRunningAll(false);
  };

  const activeScenario = mode?.source?.scenario?.id;
  const isStreaming = mode?.mode === "mock" && mode?.source?.running;
  const passCount = Object.values(results).filter((r: ScenarioRunResult) => r.verdict?.startsWith("PASS")).length;
  const scoredCount = Object.keys(results).length;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
              <FlaskConical className="w-6 h-6 text-blue-600" />
              <span>Mock Scenarios</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1 max-w-3xl">
              Controlled telemetry with known ground truth, fed through the identical validation,
              detection, fusion, localization, alert and impact pipeline that live sensors use.
              The only difference between the two modes is where the data comes from.
            </p>
          </div>
          <button
            onClick={scoreAll}
            disabled={runningAll || scenarios.length === 0}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:opacity-60 text-white text-xs font-bold rounded-xl shadow-2xs flex items-center space-x-2 transition"
          >
            {runningAll ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
            <span>{runningAll ? "Scoring…" : "Score All Scenarios"}</span>
          </button>
        </div>

        {scoredCount > 0 && (
          <p className={`mt-4 text-xs font-bold rounded-xl px-3.5 py-2.5 border ${
            passCount === scoredCount
              ? "text-emerald-700 bg-emerald-50 border-emerald-200"
              : "text-amber-800 bg-amber-50 border-amber-200"
          }`}>
            {passCount}/{scoredCount} scenarios passing
            {passCount < scoredCount && " — a failing scenario is a finding, not a bug in the harness."}
          </p>
        )}
        {error && (
          <p className="mt-3 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-2.5 font-medium">{error}</p>
        )}
        {isStreaming && (
          <p className="mt-3 text-xs text-blue-700 bg-blue-50 border border-blue-100 rounded-xl px-3.5 py-2.5 font-medium flex items-center space-x-2">
            <Radio className="w-3.5 h-3.5 shrink-0" />
            <span>
              Streaming <strong>{mode?.source?.scenario?.name}</strong> into the dashboard
              at {mode?.source?.speed}× — {mode?.sample_count} samples ingested,
              {" "}{mode?.rejected_count} rejected.
            </span>
          </p>
        )}
      </div>

      {/* Scenario grid */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {scenarios.map((s) => {
          const result = results[s.id];
          const isActive = activeScenario === s.id && isStreaming;
          const pass = result?.verdict?.startsWith("PASS");
          return (
            <div
              key={s.id}
              className={`bg-white rounded-2xl border p-5 shadow-xs transition ${
                isActive ? "border-blue-400 ring-2 ring-blue-500/15" : "border-slate-200/80"
              }`}
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center flex-wrap gap-2">
                    <h3 className="text-sm font-bold text-slate-900">{s.name}</h3>
                    {isActive && (
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-extrabold bg-blue-600 text-white">STREAMING</span>
                    )}
                    {!s.expect_detection && (
                      <span className="px-2 py-0.5 rounded-md text-[10px] font-extrabold bg-slate-100 text-slate-600 border border-slate-200">
                        CONTROL
                      </span>
                    )}
                  </div>
                  <p className="text-[11px] text-slate-500 mt-1.5 leading-relaxed">{s.description}</p>
                </div>
                {result && (
                  <span className={`shrink-0 w-7 h-7 rounded-xl flex items-center justify-center ${
                    pass ? "bg-emerald-100 text-emerald-600" : "bg-rose-100 text-rose-600"
                  }`}>
                    {pass ? <CheckCircle2 className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                  </span>
                )}
              </div>

              {/* Spec chips */}
              <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-3 text-[11px] text-slate-400 font-medium">
                <span className="flex items-center space-x-1"><Clock className="w-3 h-3" /><span>{s.duration_sec}s</span></span>
                {s.max_leak_lpm > 0 && (
                  <span className="flex items-center space-x-1"><Droplets className="w-3 h-3" /><span>{s.max_leak_lpm} L/min</span></span>
                )}
                {s.leak_count > 0 && <span>{s.leak_count} leak{s.leak_count > 1 ? "s" : ""}</span>}
                {s.fault_count > 0 && <span className="text-amber-600">{s.fault_count} fault{s.fault_count > 1 ? "s" : ""}</span>}
                {s.start_time && <span className="text-indigo-500">@ {s.start_time}</span>}
                {s.expect_zone && <span>expect {s.expect_zone}</span>}
              </div>

              {/* Result */}
              {result && (
                <div className={`mt-3.5 rounded-xl border px-3.5 py-2.5 ${
                  pass ? "bg-emerald-50/60 border-emerald-200" : "bg-rose-50/60 border-rose-200"
                }`}>
                  <p className={`text-[11px] font-bold ${pass ? "text-emerald-700" : "text-rose-700"}`}>
                    {result.verdict}
                  </p>
                  <div className="grid grid-cols-4 gap-2 mt-2 text-[11px]">
                    <Metric label="Precision" value={fmtPct(result.metrics.precision)} />
                    <Metric label="Recall" value={fmtPct(result.metrics.recall)} />
                    <Metric label="F1" value={result.metrics.f1_score?.toFixed(3) ?? "—"} />
                    <Metric label="Latency" value={result.metrics.detection_latency_sec != null ? `${result.metrics.detection_latency_sec}s` : "—"} />
                  </div>
                </div>
              )}

              <div className="flex items-center space-x-2 mt-4">
                <button
                  onClick={() => stream(s.id)}
                  disabled={busy === s.id || runningAll}
                  className="px-3 py-2 bg-slate-900 hover:bg-slate-800 disabled:opacity-50 text-white text-xs font-bold rounded-xl flex items-center space-x-1.5 transition"
                >
                  <Radio className="w-3.5 h-3.5" />
                  <span>Stream to Dashboard</span>
                </button>
                <button
                  onClick={() => score(s.id)}
                  disabled={busy === s.id || runningAll}
                  className="px-3 py-2 bg-white border border-slate-200 hover:border-blue-300 hover:text-blue-600 text-slate-700 disabled:opacity-50 text-xs font-bold rounded-xl flex items-center space-x-1.5 transition"
                >
                  {busy === s.id ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                  <span>Score</span>
                </button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Custom scenario builder — the backend already accepts an arbitrary
          ScenarioSpec, so this is a form over that, not a second code path. */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 mb-1">Custom Scenario</h3>
        <p className="text-[11px] text-slate-500 mb-4">
          Define a one-off case without touching code. Scored the same way as the built-ins.
        </p>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          <Field label="Leak (L/min)">
            <input type="number" step={0.05} min={0} value={custom.rate}
                   onChange={(e) => setCustom({ ...custom, rate: Number(e.target.value) })}
                   className={inputCls} />
          </Field>
          <Field label="Location">
            <select value={custom.location} onChange={(e) => setCustom({ ...custom, location: e.target.value })} className={inputCls}>
              <option>Main_Trunk</option><option>Branch_A</option><option>Branch_B</option>
            </select>
          </Field>
          <Field label="Ramp (s)">
            <input type="number" step={10} min={0} value={custom.ramp}
                   onChange={(e) => setCustom({ ...custom, ramp: Number(e.target.value) })}
                   className={inputCls} />
          </Field>
          <Field label="Noise σ">
            <input type="number" step={0.01} min={0} value={custom.noise}
                   onChange={(e) => setCustom({ ...custom, noise: Number(e.target.value) })}
                   className={inputCls} />
          </Field>
          <Field label="Start time">
            <input type="text" placeholder="02:00 (optional)" value={custom.startTime}
                   onChange={(e) => setCustom({ ...custom, startTime: e.target.value })}
                   className={inputCls} />
          </Field>
        </div>
        <button
          onClick={runCustom}
          disabled={busy === "__custom__"}
          className="mt-4 px-4 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-60 text-white text-xs font-bold rounded-xl flex items-center space-x-2 transition"
        >
          {busy === "__custom__" ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4" />}
          <span>Score Custom Scenario</span>
        </button>
        {results["__custom__"] && (
          <div className={`mt-3 rounded-xl border px-3.5 py-2.5 ${
            results["__custom__"].verdict?.startsWith("PASS")
              ? "bg-emerald-50/60 border-emerald-200" : "bg-rose-50/60 border-rose-200"
          }`}>
            <p className="text-[11px] font-bold text-slate-700">{results["__custom__"].verdict}</p>
            <p className="text-[11px] text-slate-500 mt-1">
              P={fmtPct(results["__custom__"].metrics.precision)} ·
              R={fmtPct(results["__custom__"].metrics.recall)} ·
              latency={results["__custom__"].metrics.detection_latency_sec ?? "—"}s
            </p>
          </div>
        )}
      </div>

      <div className="bg-slate-50 border border-slate-200 rounded-2xl px-5 py-4 flex items-start space-x-2.5">
        <Info className="w-4 h-4 text-slate-400 shrink-0 mt-0.5" />
        <p className="text-xs text-slate-500 leading-relaxed">
          Scored runs are stored with <code className="font-mono">source: "mock"</code> and feed
          Analytics and Reports as a benchmark corpus. They are excluded from operational KPIs by
          default, so synthetic leaks never inflate the water-saved figure.
        </p>
      </div>
    </div>
  );
};

const fmtPct = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : `${(v * 100).toFixed(0)}%`;

const inputCls =
  "w-full px-3 py-2 border border-slate-200 rounded-xl text-xs font-semibold text-slate-700 bg-white focus:outline-hidden focus:ring-2 focus:ring-blue-500/40";

const Field: React.FC<{ label: string; children: React.ReactNode }> = ({ label, children }) => (
  <div>
    <label className="text-[10px] font-bold text-slate-500 uppercase tracking-wider block mb-1.5">{label}</label>
    {children}
  </div>
);

const Metric: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div>
    <p className="text-[9px] font-bold text-slate-400 uppercase tracking-wider">{label}</p>
    <p className="font-extrabold text-slate-800">{value}</p>
  </div>
);
