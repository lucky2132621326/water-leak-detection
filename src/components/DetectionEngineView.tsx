import React, { useEffect, useState } from "react";
import { ShieldAlert, Zap, Moon, Activity, Cpu, Scale, Gauge } from "lucide-react";

interface DetectionEngineViewProps {
  evaluation: any;
}

const WEIGHT_ROWS = [
  { key: "mass_balance", label: "Mass Balance Weight", tone: "text-blue-600" },
  { key: "pressure_drop", label: "Pressure Drop Weight", tone: "text-rose-600" },
  { key: "current_signature", label: "Motor Current Weight", tone: "text-purple-600" },
  { key: "mnf", label: "MNF Baseline Weight", tone: "text-amber-600" },
  { key: "cusum", label: "CUSUM Drift Weight", tone: "text-emerald-600" },
];

const THRESHOLD_LABELS: Record<string, string> = {
  mass_balance_sigma: "Mass balance sigma",
  mass_balance_persistence_samples: "Persistence (samples)",
  current_drop_ma: "Current drop (mA)",
  cusum_k: "CUSUM slack k",
  cusum_h: "CUSUM decision h",
  mnf_window: "MNF night window",
};

interface PlausibilityGuardConfig {
  enabled: boolean;
  current_ma_per_leak_lpm: number;
  pressure_bar_per_leak_lpm: number;
  margin: number;
  min_residual_lpm: number;
  rule: string;
}

interface DetectorConfig {
  weights: Record<string, number>;
  formula: string;
  thresholds: Record<string, string | number>;
  plausibility_guard?: PlausibilityGuardConfig;
}

export const DetectionEngineView: React.FC<DetectionEngineViewProps> = ({ evaluation }) => {
  const [config, setConfig] = useState<DetectorConfig | null>(null);

  // Fusion weights and thresholds are config, not telemetry — fetch once.
  useEffect(() => {
    fetch("/api/detectors/config")
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => setConfig(null));
  }, []);

  const detectors = evaluation?.detectors;
  const fusion = evaluation?.fusion;
  const sensorFault = evaluation?.sensor_fault;

  const massBalance = detectors?.mass_balance;
  const currentSig = detectors?.current_signature;
  const mnf = detectors?.mnf;
  const cusum = detectors?.cusum;
  const pressureDrop = detectors?.pressure_drop;

  return (
    <div className="space-y-6">
      {/* A withheld alarm must never look like an all-clear. The flow meters are
          claiming a leak the pump and pressure channels say is impossible, which
          means an instrument has almost certainly failed — the operator needs
          that, not silence. */}
      {sensorFault?.is_fault && (
        <div className="bg-amber-50 border border-amber-300 rounded-2xl p-5">
          <h3 className="text-sm font-bold text-amber-900 flex items-center space-x-2">
            <Gauge className="w-4 h-4" />
            <span>Instrument Fault — leak alarm withheld</span>
          </h3>
          <p className="text-xs text-amber-800 mt-2 leading-relaxed">
            {sensorFault.hypothesis}
          </p>
          <p className="text-[11px] text-amber-700/90 mt-2 font-mono leading-relaxed">
            {sensorFault.detail}
          </p>
          {sensorFault.contradicting_channels?.length > 0 && (
            <p className="text-[11px] text-amber-700/80 mt-2">
              Contradicted by: {sensorFault.contradicting_channels.join(", ")}
            </p>
          )}
        </div>
      )}

      {/* Banner */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
              <ShieldAlert className="w-6 h-6 text-rose-600" />
              <span>Phase 2 & 3: Multi-Algorithm Detection & Sensor Fusion Engine</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Parallel evaluation of Mass Balance (3-Sigma), Motor Current Signatures, Minimum Night Flow, and CUSUM residual cumulative sum.
            </p>
          </div>

          <div className="flex items-center space-x-4">
            <div className="text-right">
              <div className="text-xs text-slate-400 font-medium">Fused Confidence Index</div>
              <div className="text-2xl font-black text-slate-900">
                {((fusion?.fused_confidence ?? 0) * 100).toFixed(1)}%
              </div>
            </div>
            <div className={`px-3.5 py-1.5 rounded-full text-xs font-bold border ${
              Boolean(fusion?.is_alarm)
                ? "bg-rose-100 text-rose-700 border-rose-200 animate-pulse"
                : "bg-emerald-100 text-emerald-700 border-emerald-200"
            }`}>
              {fusion?.severity || "NONE"}
            </div>
          </div>
        </div>
      </div>

      {/* 4 Detectors Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-5">
        {/* 1. Mass Balance */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(massBalance?.is_alarm) ? "border-rose-300 bg-rose-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Scale className="w-4 h-4 text-blue-600" />
              <h3 className="text-sm font-bold text-slate-900">Mass Balance (3-Sigma)</h3>
            </div>
            {(Boolean(massBalance?.is_alarm)) ? (
              <span className="text-[10px] bg-rose-600 text-white px-2 py-0.5 rounded-full font-bold">ALARM</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between text-slate-500">
              <span>Residual (ΔQ):</span>
              <span className="font-mono text-slate-900 font-bold">{massBalance?.residual ?? 0} L/min</span>
            </div>
            <div className="flex justify-between text-slate-500">
              <span>Threshold (3-Sigma):</span>
              <span className="font-mono text-slate-700 font-semibold">{massBalance?.threshold ?? 0} L/min</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-blue-600">{((massBalance?.confidence ?? 0) * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* 2. Current Signature */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(currentSig?.is_alarm) ? "border-purple-300 bg-purple-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Zap className="w-4 h-4 text-purple-600" />
              <h3 className="text-sm font-bold text-slate-900">Current Signature</h3>
            </div>
            {(Boolean(currentSig?.is_alarm)) ? (
              <span className="text-[10px] bg-purple-600 text-white px-2 py-0.5 rounded-full font-bold">ALARM</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between text-slate-500">
              <span>Current Load:</span>
              <span className="font-mono text-slate-900 font-bold">{currentSig?.current_ma ?? 0} mA</span>
            </div>
            <div className="flex justify-between text-slate-500">
              <span>Transient ΔI:</span>
              <span className="font-mono text-slate-700 font-semibold">{currentSig?.current_delta_ma ?? 0} mA</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-purple-600">{((currentSig?.confidence ?? 0) * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* 3. Minimum Night Flow (MNF) */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          mnf?.is_alarm ? "border-amber-300 bg-amber-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Moon className="w-4 h-4 text-amber-600" />
              <h3 className="text-sm font-bold text-slate-900">MNF Baseline</h3>
            </div>
            {mnf?.is_alarm ? (
              <span className="text-[10px] bg-amber-600 text-white px-2 py-0.5 rounded-full font-bold">ALARM</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between text-slate-500">
              <span>Quiet Baseline:</span>
              <span className="font-mono text-slate-900 font-bold">0.00 L/min</span>
            </div>
            <div className="flex justify-between text-slate-500">
              <span>Night Residual:</span>
              <span className="font-mono text-slate-700 font-semibold">{mnf?.residual ?? 0.12} L/min</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-amber-600">{((mnf?.confidence ?? 0.700) * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* 4. CUSUM */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(cusum?.is_alarm) ? "border-emerald-300 bg-emerald-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900">CUSUM Micro-Leak</h3>
            </div>
            {Boolean(cusum?.is_alarm) ? (
              <span className="text-[10px] bg-amber-500 text-white px-2 py-0.5 rounded-full font-bold">SUSPECT</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between text-slate-500">
              <span>Accumulated Score:</span>
              <span className="font-mono text-slate-900 font-bold">{cusum?.score ?? 0}</span>
            </div>
            <div className="flex justify-between text-slate-500">
              <span>Decision Threshold h:</span>
              <span className="font-mono text-slate-700 font-semibold">3.00</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-emerald-600">{((cusum?.confidence ?? 0) * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* 5. Pressure Drop — only present when the rig has a real transducer */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(pressureDrop?.is_alarm) ? "border-rose-300 bg-rose-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Gauge className="w-4 h-4 text-rose-600" />
              <h3 className="text-sm font-bold text-slate-900">Pressure Drop</h3>
            </div>
            {!pressureDrop?.active ? (
              <span className="text-[10px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full font-bold">INACTIVE</span>
            ) : Boolean(pressureDrop?.is_alarm) ? (
              <span className="text-[10px] bg-rose-600 text-white px-2 py-0.5 rounded-full font-bold">ALARM</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between text-slate-500">
              <span>Line Pressure:</span>
              <span className="font-mono text-slate-900 font-bold">
                {pressureDrop?.pressure_bar != null ? `${pressureDrop.pressure_bar} bar` : "—"}
              </span>
            </div>
            <div className="flex justify-between text-slate-500">
              <span>Baseline / Drop:</span>
              <span className="font-mono text-slate-700 font-semibold">
                {pressureDrop?.baseline_bar != null ? `${pressureDrop.baseline_bar} / ${pressureDrop.drop_bar}` : "—"}
              </span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-rose-600">
                {((pressureDrop?.confidence ?? 0) * 100).toFixed(1)}%
              </span>
            </div>
            {!pressureDrop?.active && (
              <p className="text-[10px] text-slate-400 leading-snug pt-1">
                No measured pressure — inactive so it cannot double-count the flow signal.
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Fusion weights — fetched from /api/detectors/config so the formula
          shown is the one the engine is actually running. It previously
          hardcoded 0.20 for Current and MNF, which did not match the code. */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 mb-2 flex items-center space-x-2">
          <Cpu className="w-4 h-4 text-blue-600" />
          <span>Multi-Sensor Confidence Fusion Algorithm Weights</span>
        </h3>
        <p className="text-xs text-slate-500 mb-5 font-mono">
          {config
            ? `Confidence = ${config.formula}`
            : "Loading fusion configuration…"}
        </p>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4 text-xs">
          {WEIGHT_ROWS.map(({ key, label, tone }) => (
            <div key={key} className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
              <div className="text-slate-500 font-medium">{label}</div>
              <div className={`text-xl font-extrabold mt-1 ${tone}`}>
                {config?.weights?.[key] != null
                  ? `${(config.weights[key] * 100).toFixed(0)}%`
                  : "—"}
              </div>
            </div>
          ))}
        </div>

        {config?.thresholds && (
          <div className="mt-5 pt-5 border-t border-slate-100 grid grid-cols-2 md:grid-cols-3 gap-3 text-[11px]">
            {Object.entries(config.thresholds).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-slate-400 font-medium">{THRESHOLD_LABELS[k] ?? k}</span>
                <span className="font-mono font-bold text-slate-700">{String(v)}</span>
              </div>
            ))}
          </div>
        )}

        {/* The guard can veto a fused alarm, so publishing the weights alone
            would overstate what decides an alarm. */}
        {config?.plausibility_guard && (
          <div className="mt-5 pt-5 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-slate-900 flex items-center space-x-2">
                <Scale className="w-4 h-4 text-indigo-600" />
                <span>Physical Plausibility Guard</span>
              </span>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                  config.plausibility_guard.enabled
                    ? "bg-indigo-50 text-indigo-700"
                    : "bg-slate-100 text-slate-500"
                }`}
              >
                {config.plausibility_guard.enabled ? "ACTIVE" : "DISABLED"}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              {config.plausibility_guard.rule}
            </p>
            <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-400 font-medium">Current per L/min</span>
                <span className="font-mono font-bold text-slate-700">
                  {config.plausibility_guard.current_ma_per_leak_lpm} mA
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400 font-medium">Pressure per L/min</span>
                <span className="font-mono font-bold text-slate-700">
                  {config.plausibility_guard.pressure_bar_per_leak_lpm} bar
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400 font-medium">Veto margin</span>
                <span className="font-mono font-bold text-slate-700">
                  {config.plausibility_guard.margin}×
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400 font-medium">Never veto below</span>
                <span className="font-mono font-bold text-slate-700">
                  {config.plausibility_guard.min_residual_lpm} L/min
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
