import React, { useCallback, useEffect, useState } from "react";
import { Play, Square, Droplets, MapPin, Loader2, Info, Radio } from "lucide-react";
import type { OperatingMode } from "../types";

const LOCATIONS = ["Main_Trunk", "Branch_A", "Branch_B"];
const PRESETS: { label: string; lpm: number }[] = [
  { label: "Small", lpm: 0.5 },
  { label: "Medium", lpm: 1.25 },
  { label: "Large", lpm: 2.5 },
];

interface LeakControlState {
  active: boolean;
  overriding: boolean;
  rate_lpm: number;
  effective_rate_lpm: number;
  location: string;
  ramp_sec: number;
}

/**
 * Interactive injection belongs to Test Bench. The physical rig uses
 * manual clamp openings, so Live Sensor Mode shows the experiment procedure
 * instead of exposing a fictional electronic leak-valve control.
 */
export const LeakBenchControls: React.FC<{ mode: OperatingMode; onChanged?: () => void }> = ({
  mode, onChanged,
}) => {
  const [control, setControl] = useState<LeakControlState | null>(null);
  const [available, setAvailable] = useState(false);
  const [rate, setRate] = useState(1.25);
  const [location, setLocation] = useState("Main_Trunk");
  const [ramp, setRamp] = useState(0);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);

  const refresh = useCallback(() => {
    if (mode !== "mock") { setAvailable(false); setControl(null); return; }
    fetch("/api/mock/control")
      .then((r) => r.json())
      .then((d) => {
        setAvailable(Boolean(d.available));
        setControl(d.leak_control ?? null);
        if (d.leak_control?.location) setLocation(d.leak_control.location);
      })
      .catch(() => setAvailable(false));
  }, [mode]);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, 2000);
    return () => clearInterval(t);
  }, [refresh]);

  const send = (body: any) => {
    setBusy(true);
    fetch("/api/leak/toggle", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((d) => {
        setMessage({ ok: Boolean(d.success), text: d.message ?? d.error ?? "" });
        if (d.leak_control) setControl(d.leak_control);
        refresh();
        onChanged?.();
      })
      .catch(() => setMessage({ ok: false, text: "Backend unreachable." }))
      .finally(() => setBusy(false));
  };

  const leaking = Boolean(control?.active) || false;

  if (mode === "live") {
    return (
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
          <Radio className="w-4 h-4 text-blue-600" />
          <span>Physical Leak Experiment</span>
        </h3>
        <p className="mt-2 text-xs text-slate-600 leading-relaxed">
          Live leaks are created manually with the calibrated worm-drive clamps;
          this rig has no electronic leak solenoid. Start an experiment, record
          the clamp opening in <strong>Experiment Control</strong>, then open or
          close the physical clamp. Telemetry and localization remain automatic.
        </p>
        <p className="mt-3 text-[10px] text-amber-700 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5">
          This dashboard does not issue operational valve-control instructions.
        </p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-5">
        <div>
          <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <Droplets className="w-4 h-4 text-blue-600" />
            <span>Leak Injection Bench</span>
          </h3>
          <p className="text-[11px] text-slate-500 mt-1 max-w-2xl">
            Changes the generated telemetry immediately. The resulting samples run
            through the identical validation and detection pipeline as live sensors.
          </p>
        </div>
        <span className={`px-2.5 py-1 rounded-lg text-[10px] font-extrabold border shrink-0 ${
          leaking ? "bg-rose-100 text-rose-700 border-rose-200 animate-pulse"
                  : "bg-emerald-100 text-emerald-700 border-emerald-200"
        }`}>
          {leaking ? `LEAKING · ${control?.effective_rate_lpm} L/min` : "NO LEAK"}
        </span>
      </div>

      {mode === "mock" && !available ? (
        <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5">
          No mock stream is running. Start one from <strong>Mock Scenarios</strong> — the
          “Manual Control (free run)” scenario is the one built for interactive testing.
        </p>
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
            {/* Location */}
            <div>
              <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider block mb-2 flex items-center space-x-1.5">
                <MapPin className="w-3 h-3" /><span>Leak Location</span>
              </label>
              <div className="grid grid-cols-3 gap-1.5">
                {LOCATIONS.map((l) => (
                  <button
                    key={l}
                    onClick={() => setLocation(l)}
                    className={`px-2 py-2 rounded-xl text-[11px] font-bold border transition ${
                      location === l
                        ? "bg-blue-600 text-white border-blue-600"
                        : "bg-white text-slate-600 border-slate-200 hover:border-blue-300"
                    }`}
                  >
                    {l.replace("_", " ")}
                  </button>
                ))}
              </div>
            </div>

            {/* Rate */}
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Leak Rate</label>
                <span className="text-sm font-extrabold text-blue-600 font-mono">{rate.toFixed(2)} L/min</span>
              </div>
              <input
                type="range" min={0.05} max={5} step={0.05} value={rate}
                onChange={(e) => setRate(Number(e.target.value))}
                className="w-full accent-blue-600 cursor-pointer"
              />
              <div className="grid grid-cols-3 gap-1.5 mt-2">
                {PRESETS.map((p) => (
                  <button
                    key={p.label}
                    onClick={() => setRate(p.lpm)}
                    className={`px-2 py-1.5 rounded-lg text-[11px] font-bold border transition ${
                      Math.abs(rate - p.lpm) < 0.01
                        ? "bg-slate-900 text-white border-slate-900"
                        : "bg-white text-slate-600 border-slate-200 hover:border-slate-400"
                    }`}
                  >
                    {p.label} ({p.lpm})
                  </button>
                ))}
              </div>
            </div>

            {/* Ramp */}
            <div>
              <div className="flex items-baseline justify-between mb-2">
                <label className="text-[11px] font-bold text-slate-500 uppercase tracking-wider">Onset</label>
                <span className="text-[11px] font-semibold text-slate-500">
                  {ramp === 0 ? "sudden" : `ramp ${ramp}s`}
                </span>
              </div>
              <input
                type="range" min={0} max={180} step={10} value={ramp}
                onChange={(e) => setRamp(Number(e.target.value))}
                className="w-full accent-blue-600 cursor-pointer"
              />
              <p className="text-[10px] text-slate-400 mt-2 leading-snug">
                A ramp grows the leak gradually — harder for threshold detectors,
                which is what CUSUM is for.
              </p>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 mt-5 pt-5 border-t border-slate-100">
            <button
              onClick={() => send({ action: "OPEN", size: rate, location, ramp_sec: ramp })}
              disabled={busy}
              className="px-4 py-2.5 bg-rose-600 hover:bg-rose-700 disabled:opacity-60 text-white text-xs font-bold rounded-xl flex items-center space-x-2 transition shadow-md shadow-rose-600/20"
            >
              {busy ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 fill-current" />}
              <span>{leaking ? "Update Leak" : "Start Leak"}</span>
            </button>
            <button
              onClick={() => send({ action: "CLOSE" })}
              disabled={busy || !leaking}
              className="px-4 py-2.5 bg-slate-900 hover:bg-slate-800 disabled:opacity-40 text-white text-xs font-bold rounded-xl flex items-center space-x-2 transition"
            >
              <Square className="w-4 h-4 fill-current" />
              <span>Stop Leak</span>
            </button>
            {mode === "mock" && control?.overriding && (
              <button
                onClick={() => {
                  setBusy(true);
                  fetch("/api/mock/control/release", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" })
                    .then((r) => r.json())
                    .then((d) => { if (d.leak_control) setControl(d.leak_control); setMessage({ ok: true, text: "Manual control released — the scenario script resumes." }); })
                    .finally(() => { setBusy(false); refresh(); });
                }}
                className="px-3.5 py-2.5 bg-white border border-slate-200 hover:border-slate-400 text-slate-600 text-xs font-bold rounded-xl transition"
              >
                Release to Scenario
              </button>
            )}
          </div>

          {message && (
            <p className={`mt-3 text-[11px] font-medium rounded-xl px-3.5 py-2.5 border ${
              message.ok ? "text-emerald-700 bg-emerald-50 border-emerald-200"
                         : "text-rose-700 bg-rose-50 border-rose-200"
            }`}>
              {message.text}
            </p>
          )}

          <p className="mt-3 text-[10px] text-slate-400 flex items-start space-x-1.5 leading-relaxed">
            {mode === "live" ? <Radio className="w-3 h-3 shrink-0 mt-0.5" /> : <Info className="w-3 h-3 shrink-0 mt-0.5" />}
            <span>
              {mode === "live"
                ? "Live Sensor Mode — commands are published to rig/cmd and require a reachable broker and a powered rig."
                : "Test Bench — the change appears in the very next generated sample; detection latency you observe is the detector's, not the harness's."}
            </span>
          </p>
        </>
      )}
    </div>
  );
};
