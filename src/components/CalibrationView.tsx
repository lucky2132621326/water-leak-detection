import React, { useEffect, useState } from "react";
import { CheckCircle2, Save, Sliders, TriangleAlert } from "lucide-react";

type CalibrationForm = {
  flow1_k: number;
  flow2_k: number;
  flow3_k: number;
  bias_lpm: number;
  sigma_lpm: number;
  vib_baseline_band_mid: number;
  temp_k_coeff: number;
};

const initial: CalibrationForm = {
  flow1_k: 450, flow2_k: 450, flow3_k: 450, bias_lpm: 0.02, sigma_lpm: 0.03,
  vib_baseline_band_mid: 0.015, temp_k_coeff: 0.0,
};

export const CalibrationView: React.FC = () => {
  const [form, setForm] = useState(initial);
  const [status, setStatus] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetch("/api/calibration")
      .then((response) => response.json())
      .then((data) => setForm({
        flow1_k: Number(data.flow1_k), flow2_k: Number(data.flow2_k), flow3_k: Number(data.flow3_k),
        bias_lpm: Number(data.bias_lpm), sigma_lpm: Number(data.sigma_lpm),
        vib_baseline_band_mid: Number(data.vib_baseline_band_mid ?? 0.015),
        temp_k_coeff: Number(data.temp_k_coeff ?? 0.0),
      }))
      .catch(() => setStatus("Calibration service unavailable."));
  }, []);

  const update = (key: keyof CalibrationForm, value: string) => setForm((current) => ({ ...current, [key]: Number(value) }));

  const save = async () => {
    setSaving(true);
    setStatus(null);
    try {
      const response = await fetch("/api/calibration", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(form) });
      const result = await response.json();
      if (!response.ok || !result.success) throw new Error(result.error || "Save failed");
      setStatus("Calibration saved; detection pipelines were re-armed with the new bias and sigma.");
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Calibration save failed.");
    } finally {
      setSaving(false);
    }
  };

  const sensors = [
    { key: "flow1_k" as const, label: "Flow 1 · Q_in", gpio: 34 },
    { key: "flow2_k" as const, label: "Flow 2 · Q_out", gpio: 35 },
    { key: "flow3_k" as const, label: "Flow 3 · Q_branch", gpio: 32 },
  ];

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4 mb-6">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2"><Sliders className="w-6 h-6 text-blue-600" /><span>Commissioning Calibration</span></h2>
            <p className="text-xs text-slate-500 mt-1">Runtime source of truth for flow conversion and the zero-leak detection baseline.</p>
          </div>
          <button disabled={saving} onClick={() => void save()} className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 disabled:bg-slate-300 text-white text-xs font-bold rounded-xl shadow-md shadow-blue-600/20 flex items-center space-x-2">
            <Save className="w-4 h-4" /><span>{saving ? "Saving…" : "Save & re-arm detectors"}</span>
          </button>
        </div>

        {status && <div className="mb-5 rounded-xl border border-blue-200 bg-blue-50 p-3 text-xs font-semibold text-blue-800 flex gap-2"><CheckCircle2 className="w-4 h-4 shrink-0" />{status}</div>}

        <div className="grid grid-cols-1 md:grid-cols-3 gap-5 mb-6">
          {sensors.map((sensor) => (
            <label key={sensor.key} className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 text-xs font-bold text-slate-700">
              {sensor.label}<span className="block text-[11px] font-medium text-slate-400 mt-1">YF-S201 interrupt · GPIO {sensor.gpio}</span>
              <span className="block text-[11px] text-slate-500 mt-4 mb-1">Pulses per litre</span>
              <input type="number" min="100" max="2000" step="0.1" value={form[sensor.key]} onChange={(event) => update(sensor.key, event.target.value)} className="w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold text-slate-900" />
            </label>
          ))}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          <label className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 text-xs font-bold text-slate-700">Zero-leak residual bias
            <span className="block text-[11px] font-medium text-slate-500 mt-1">Mean of Q_in − Q_out during the commissioned zero-leak run.</span>
            <input type="number" step="0.001" value={form.bias_lpm} onChange={(event) => update("bias_lpm", event.target.value)} className="mt-3 w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold" />
          </label>
          <label className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 text-xs font-bold text-slate-700">Baseline residual sigma
            <span className="block text-[11px] font-medium text-slate-500 mt-1">Standard deviation used by the 3σ mass-balance detector.</span>
            <input type="number" min="0.001" step="0.001" value={form.sigma_lpm} onChange={(event) => update("sigma_lpm", event.target.value)} className="mt-3 w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold" />
          </label>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-5 mt-5">
          <label className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 text-xs font-bold text-slate-700">Acoustic baseline (band-mid)
            <span className="block text-[11px] font-medium text-slate-500 mt-1">Clean-running MPU6050 band_mid energy (50-150 Hz). The acoustic detector alarms on the ratio of live readings to this value, not a raw threshold. PROVISIONAL — no real sensor characterised yet.</span>
            <input type="number" min="0.0001" step="0.0001" value={form.vib_baseline_band_mid} onChange={(event) => update("vib_baseline_band_mid", event.target.value)} className="mt-3 w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold" />
          </label>
          <label className="bg-slate-50 border border-slate-200/70 rounded-2xl p-5 text-xs font-bold text-slate-700">Temperature K-factor coefficient
            <span className="block text-[11px] font-medium text-slate-500 mt-1">Corrects flow bias for pump-warming drift (DS18B20). Defaults to 0.0 (no-op) until characterised over a long run.</span>
            <input type="number" step="0.001" value={form.temp_k_coeff} onChange={(event) => update("temp_k_coeff", event.target.value)} className="mt-3 w-full bg-white border border-slate-200 rounded-xl px-3 py-2 text-sm font-bold" />
          </label>
        </div>

        <div className="mt-6 rounded-xl border border-amber-200 bg-amber-50 p-4 text-[11px] leading-relaxed text-amber-900 flex gap-2">
          <TriangleAlert className="w-4 h-4 shrink-0" /> Backend values update immediately. ESP32 K-factors are stored independently in NVS; synchronize them during supervised USB commissioning before collecting physical benchmark data.
        </div>
      </div>
    </div>
  );
};
