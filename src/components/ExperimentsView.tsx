import React, { useEffect, useMemo, useState } from "react";
import { CheckCircle2, Clock3, FlaskConical, MapPin, Radio, Square } from "lucide-react";
import type { SystemHealth } from "../types";

interface ExperimentsViewProps {
  mode: "live" | "replay";
  health: SystemHealth | null;
}

const turnsOptions = ["0.25", "0.50", "0.75", "1.00"];

export const ExperimentsView: React.FC<ExperimentsViewProps> = ({ mode, health }) => {
  const [calibration, setCalibration] = useState<any>(null);
  const [activeEvent, setActiveEvent] = useState<any>(null);
  const [teeId, setTeeId] = useState("TEE_A");
  const [clampTurns, setClampTurns] = useState("0.50");
  const [demandMode, setDemandMode] = useState("steady");
  const [notes, setNotes] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = async () => {
    try {
      const [calibrationResponse, statusResponse] = await Promise.all([
        fetch("/api/calibration"),
        fetch("/api/ground-truth/status"),
      ]);
      if (calibrationResponse.ok) setCalibration(await calibrationResponse.json());
      if (statusResponse.ok) {
        const status = await statusResponse.json();
        setActiveEvent(status.active ? status.event : null);
      }
    } catch {
      setMessage("Ground-truth service is unavailable.");
    }
  };

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), 2000);
    return () => clearInterval(interval);
  }, []);

  const leakLpm = useMemo(() => {
    const value = calibration?.clamp_calibration?.[teeId]?.[clampTurns];
    return Number(value ?? 0);
  }, [calibration, teeId, clampTurns]);

  const realRigReady = mode === "live" && Boolean(health?.device?.online) && !health?.simulation_mode;

  const post = async (path: string, body?: object) => {
    setBusy(true);
    setMessage(null);
    try {
      const response = await fetch(path, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body || {}),
      });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.error || "Request failed");
      setActiveEvent(path.endsWith("start") ? result.event : null);
      setMessage(path.endsWith("start")
        ? `Physical event timestamp captured at ${new Date(result.event.start_ts * 1000).toLocaleTimeString()}.`
        : `Event closed after ${result.event.duration_sec}s; ground truth is stored in MongoDB.`);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Ground-truth request failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
            <FlaskConical className="w-6 h-6 text-purple-600" />
            <span>Physical Ground-Truth Laboratory</span>
          </h2>
          <p className="text-xs text-slate-500 mt-1 max-w-3xl">
            Records the operator-observed start and stop of a real calibrated clamp leak. This does not actuate pumps, valves, or the servo.
          </p>
        </div>
        <span className={`px-3 py-2 rounded-xl border text-xs font-bold flex items-center gap-2 ${realRigReady ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "bg-amber-50 border-amber-200 text-amber-800"}`}>
          <Radio className="w-4 h-4" /> {realRigReady ? "REAL RIG VERIFIED" : "LIVE HARDWARE REQUIRED"}
        </span>
      </div>

      {message && (
        <div className="bg-indigo-50 border border-indigo-200 text-indigo-800 p-3.5 rounded-2xl text-xs font-semibold flex items-center space-x-2">
          <CheckCircle2 className="w-4 h-4 shrink-0" /><span>{message}</span>
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-5">
            <div>
              <h3 className="text-sm font-bold text-slate-900">Event metadata</h3>
              <p className="text-[11px] text-slate-500 mt-1">Calibrated leak rate is filled from the selected tee and clamp position.</p>
            </div>
            <span className="text-[10px] font-bold text-amber-700 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1">
              {calibration?.clamp_calibration_status || "CALIBRATION NOT LOADED"}
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <label className="text-xs font-bold text-slate-700">Physical tee
              <select value={teeId} onChange={(event) => setTeeId(event.target.value)} disabled={Boolean(activeEvent)} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm">
                <option value="TEE_A">TEE A</option><option value="TEE_B">TEE B</option><option value="TEE_C">TEE C</option>
              </select>
            </label>
            <label className="text-xs font-bold text-slate-700">Clamp opening (turns)
              <select value={clampTurns} onChange={(event) => setClampTurns(event.target.value)} disabled={Boolean(activeEvent)} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm">
                {turnsOptions.map((turns) => <option key={turns} value={turns}>{turns} turns</option>)}
              </select>
            </label>
            <label className="text-xs font-bold text-slate-700">Calibrated leak rate
              <div className="mt-2 rounded-xl border border-purple-200 bg-purple-50 px-3 py-2.5 text-sm font-black text-purple-700">{leakLpm.toFixed(2)} L/min</div>
            </label>
            <label className="text-xs font-bold text-slate-700">Demand mode
              <select value={demandMode} onChange={(event) => setDemandMode(event.target.value)} disabled={Boolean(activeEvent)} className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm">
                <option value="steady">Steady demand</option><option value="variable">Variable demand</option>
              </select>
            </label>
          </div>

          <label className="block text-xs font-bold text-slate-700 mt-4">Operator notes
            <input value={notes} onChange={(event) => setNotes(event.target.value)} disabled={Boolean(activeEvent)} placeholder="Observed conditions, clamp setup, anomalies…" className="mt-2 w-full rounded-xl border border-slate-200 bg-slate-50 px-3 py-2.5 text-sm" />
          </label>

          <div className="mt-6 pt-5 border-t border-slate-100">
            {!activeEvent ? (
              <button disabled={!realRigReady || busy || leakLpm <= 0} onClick={() => void post("/api/ground-truth/start", { tee_id: teeId, clamp_turns: Number(clampTurns), leak_lpm: leakLpm, demand_mode: demandMode, notes })} className="rounded-xl bg-rose-600 px-5 py-3 text-xs font-black text-white shadow-md shadow-rose-600/20 disabled:cursor-not-allowed disabled:bg-slate-300 disabled:shadow-none">
                LOG PHYSICAL LEAK EVENT
              </button>
            ) : (
              <button disabled={busy} onClick={() => void post("/api/ground-truth/stop")} className="rounded-xl bg-emerald-600 px-5 py-3 text-xs font-black text-white shadow-md shadow-emerald-600/20">
                STOP & SAVE EVENT
              </button>
            )}
          </div>
        </div>

        <div className={`rounded-2xl border p-6 shadow-xs ${activeEvent ? "bg-rose-50 border-rose-200" : "bg-white border-slate-200/80"}`}>
          <h3 className="text-sm font-bold text-slate-900 flex items-center gap-2"><Clock3 className="w-4 h-4 text-purple-600" /> Capture state</h3>
          {activeEvent ? (
            <div className="mt-5 space-y-4">
              <div className="flex items-center gap-2 text-rose-700 text-xs font-black"><span className="w-2.5 h-2.5 rounded-full bg-rose-500 animate-pulse" /> RECORDING GROUND TRUTH</div>
              <div className="space-y-2 text-xs text-slate-700">
                <div className="flex justify-between"><span>Run</span><strong className="font-mono">{activeEvent.run_id}</strong></div>
                <div className="flex justify-between"><span>Tee</span><strong>{activeEvent.tee_id}</strong></div>
                <div className="flex justify-between"><span>Leak rate</span><strong>{activeEvent.leak_lpm} L/min</strong></div>
                <div className="flex justify-between"><span>Started</span><strong>{new Date(activeEvent.start_ts * 1000).toLocaleTimeString()}</strong></div>
              </div>
            </div>
          ) : (
            <div className="mt-8 text-center text-slate-500 text-xs">
              <MapPin className="w-8 h-8 mx-auto mb-3 text-slate-300" />
              No physical event is being recorded. Prepare the clamp, then use the logger at the exact observed start time.
            </div>
          )}
          <div className="mt-6 rounded-xl border border-slate-200 bg-white/70 p-3 text-[10px] leading-relaxed text-slate-500 flex gap-2">
            <Square className="w-3.5 h-3.5 shrink-0 mt-0.5" /> Timestamps are captured server-side with millisecond precision and become the benchmark truth for precision, recall, and latency.
          </div>
        </div>
      </div>
    </div>
  );
};
