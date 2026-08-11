import React, { useEffect, useState } from "react";
import { Sliders, Save, RefreshCw, CheckCircle2, ShieldAlert } from "lucide-react";

export const CalibrationView: React.FC = () => {
  const [k1, setK1] = useState(456.0);
  const [k2, setK2] = useState(448.0);
  const [k3, setK3] = useState(452.0);
  const [bias, setBias] = useState(0.02);
  const [sigma, setSigma] = useState(0.03);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load the persisted calibration record rather than showing constants.
  useEffect(() => {
    fetch("/api/calibration")
      .then((r) => r.json())
      .then((d) => {
        if (typeof d?.flow1_k === "number") setK1(d.flow1_k);
        if (typeof d?.flow2_k === "number") setK2(d.flow2_k);
        if (typeof d?.flow3_k === "number") setK3(d.flow3_k);
        if (typeof d?.bias_lpm === "number") setBias(d.bias_lpm);
        if (typeof d?.sigma_lpm === "number") setSigma(d.sigma_lpm);
        if (d?.note) setNote(d.note);
      })
      .catch(() => setError("Could not load stored calibration."));
  }, []);

  const handleSave = () => {
    setBusy(true);
    setError(null);
    fetch("/api/calibration", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        flow1_k: k1, flow2_k: k2, flow3_k: k3, bias_lpm: bias, sigma_lpm: sigma,
      }),
    })
      .then((r) => r.json())
      .then((d) => {
        if (d?.success) {
          setSaved(true);
          if (d.note) setNote(d.note);
          setTimeout(() => setSaved(false), 2500);
        } else {
          setError(d?.error ?? "Save failed.");
        }
      })
      .catch(() => setError("Backend unreachable — calibration not saved."))
      .finally(() => setBusy(false));
  };

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
              <Sliders className="w-6 h-6 text-blue-600" />
              <span>Sensor & Hardware Rig Calibration</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Calibrate YF-S201 pulse factors (K-factor), zero-leak baseline bias, and INA219 load models.
            </p>
          </div>
          <button
            onClick={handleSave}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-md shadow-blue-600/20 flex items-center space-x-2 transition"
          >
            {busy ? <RefreshCw className="w-4 h-4 animate-spin" /> : saved ? <CheckCircle2 className="w-4 h-4 text-emerald-300" /> : <Save className="w-4 h-4" />}
            <span>{busy ? "Saving…" : saved ? "Saved" : "Save Calibration"}</span>
          </button>
        </div>

        {error && (
          <p className="mb-4 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-2.5 font-medium">{error}</p>
        )}
        {note && (
          <p className="mb-5 text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-xl px-3.5 py-2.5 leading-relaxed">
            <strong>Note:</strong> {note}
          </p>
        )}

        {/* Pulse Factors Matrix */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
          <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 space-y-3">
            <div className="text-xs font-bold text-slate-700">Flow 1 Meter (Qin - Inlet)</div>
            <div className="text-[11px] text-slate-400">YF-S201 Interrupt GPIO 34</div>
            <div>
              <label className="text-xs text-slate-500 block mb-1 font-medium">Pulses / Liter Factor (K1)</label>
              <input
                type="number"
                step="0.1"
                value={k1}
                onChange={(e) => setK1(parseFloat(e.target.value))}
                className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 space-y-3">
            <div className="text-xs font-bold text-slate-700">Flow 2 Meter (Qout - Outlet)</div>
            <div className="text-[11px] text-slate-400">YF-S201 Interrupt GPIO 35</div>
            <div>
              <label className="text-xs text-slate-500 block mb-1 font-medium">Pulses / Liter Factor (K2)</label>
              <input
                type="number"
                step="0.1"
                value={k2}
                onChange={(e) => setK2(parseFloat(e.target.value))}
                className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>

          <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 space-y-3">
            <div className="text-xs font-bold text-slate-700">Flow 3 Meter (Qbranch - Side)</div>
            <div className="text-[11px] text-slate-400">YF-S201 Interrupt GPIO 32</div>
            <div>
              <label className="text-xs text-slate-500 block mb-1 font-medium">Pulses / Liter Factor (K3)</label>
              <input
                type="number"
                step="0.1"
                value={k3}
                onChange={(e) => setK3(parseFloat(e.target.value))}
                className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
        </div>

        {/* Bias & Noise Bounds */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 space-y-3">
            <div className="text-xs font-bold text-slate-700">Zero-Leak Flow Bias (LPM)</div>
            <p className="text-[11px] text-slate-500">Systemic offset between inlet and outlet meters during closed loop recirculation.</p>
            <input
              type="number"
              step="0.01"
              value={bias}
              onChange={(e) => setBias(parseFloat(e.target.value))}
              className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>

          <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 space-y-3">
            <div className="text-xs font-bold text-slate-700">Baseline Residual Sigma (Noise Std Dev)</div>
            <p className="text-[11px] text-slate-500">Standard deviation of residual noise under normal 12V pump operation.</p>
            <input
              type="number"
              step="0.01"
              value={sigma}
              onChange={(e) => setSigma(parseFloat(e.target.value))}
              className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-900 focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
          </div>
        </div>
      </div>
    </div>
  );
};
