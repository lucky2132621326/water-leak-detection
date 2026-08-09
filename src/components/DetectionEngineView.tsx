import React from "react";
import { ShieldAlert, Zap, Moon, Activity, Cpu, Scale } from "lucide-react";

interface DetectionEngineViewProps {
  evaluation: any;
}

export const DetectionEngineView: React.FC<DetectionEngineViewProps> = ({ evaluation }) => {
  const detectors = evaluation?.detectors;
  const fusion = evaluation?.fusion;

  const massBalance = detectors?.mass_balance;
  const currentSig = detectors?.current_signature;
  const mnf = detectors?.mnf;
  const cusum = detectors?.cusum;

  return (
    <div className="space-y-6">
      {/* Banner */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
              <ShieldAlert className="w-6 h-6 text-rose-600" />
              <span>Explainable Detection & Sensor Fusion</span>
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
              fusion?.is_alarm ?? false
                ? "bg-rose-100 text-rose-700 border-rose-200 animate-pulse"
                : "bg-emerald-100 text-emerald-700 border-emerald-200"
            }`}>
              {fusion?.is_alarm ? (fusion?.severity || "ALARM") : "MONITORING"}
            </div>
          </div>
        </div>
      </div>

      <div className={`border rounded-2xl p-5 ${evaluation?.is_alarm ? "bg-rose-50 border-rose-200" : "bg-emerald-50 border-emerald-200"}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className={`text-xs font-black uppercase tracking-wider ${evaluation?.is_alarm ? "text-rose-700" : "text-emerald-700"}`}>
              {evaluation?.is_alarm ? "Likely leak event" : "No confirmed event"}
            </div>
            <p className="text-sm font-semibold text-slate-800 mt-1">{evaluation?.evidence || "Waiting for an evaluated telemetry sample."}</p>
          </div>
          <div className="text-right text-xs text-slate-600">
            <div><span className="font-bold">Zone:</span> {evaluation?.zone || "NONE"}</div>
            <div><span className="font-bold">Window:</span> {evaluation?.time_window ? `${evaluation.time_window.duration_sec}s` : "not active"}</div>
          </div>
        </div>
        <p className="text-[11px] text-slate-500 mt-3">{evaluation?.false_positive_warning?.disclaimer || "Results are indicative only; field verification is required."}</p>
      </div>

      {/* 4 Detectors Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* 1. Mass Balance */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          massBalance?.is_alarm ?? false ? "border-rose-300 bg-rose-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Scale className="w-4 h-4 text-blue-600" />
              <h3 className="text-sm font-bold text-slate-900">Mass Balance (3-Sigma)</h3>
            </div>
            {(massBalance?.is_alarm ?? false) ? (
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
          currentSig?.is_alarm ?? false ? "border-purple-300 bg-purple-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Zap className="w-4 h-4 text-purple-600" />
              <h3 className="text-sm font-bold text-slate-900">Current Signature</h3>
            </div>
            {(currentSig?.is_alarm ?? false) ? (
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
              <span className="font-mono text-slate-700 font-semibold">{mnf?.residual ?? 0} L/min</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-amber-600">{((mnf?.confidence ?? 0) * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>

        {/* 4. CUSUM */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          cusum?.is_alarm ?? false ? "border-emerald-300 bg-emerald-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900">CUSUM Micro-Leak</h3>
            </div>
            {(cusum?.is_alarm ?? false) ? (
              <span className="text-[10px] bg-amber-500 text-white px-2 py-0.5 rounded-full font-bold">SUSPECT</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between text-slate-500">
              <span>Accumulated Score:</span>
              <span className="font-mono text-slate-900 font-bold">{cusum?.cusum_score ?? 0}</span>
            </div>
            <div className="flex justify-between text-slate-500">
              <span>Decision Threshold h:</span>
              <span className="font-mono text-slate-700 font-semibold">{cusum?.threshold_h ?? 0}</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-emerald-600">{((cusum?.confidence ?? 0) * 100).toFixed(1)}%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Fusion Engine Card */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 mb-2 flex items-center space-x-2">
          <Cpu className="w-4 h-4 text-blue-600" />
          <span>Multi-Sensor Confidence Fusion Algorithm Weights</span>
        </h3>
        <p className="text-xs text-slate-500 mb-5 font-mono">
          Confidence = 0.40 × C_MassBalance + 0.25 × C_Current + 0.20 × C_CUSUM + 0.15 × C_MNF
        </p>

        <div className="grid grid-cols-1 md:grid-cols-4 gap-4 text-xs">
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
            <div className="text-slate-500 font-medium">Mass Balance Weight</div>
            <div className="text-xl font-extrabold text-blue-600 mt-1">40%</div>
          </div>
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
            <div className="text-slate-500 font-medium">Motor Current Weight</div>
            <div className="text-xl font-extrabold text-purple-600 mt-1">25%</div>
          </div>
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
            <div className="text-slate-500 font-medium">MNF Baseline Weight</div>
            <div className="text-xl font-extrabold text-amber-600 mt-1">15%</div>
          </div>
          <div className="bg-slate-50 p-4 rounded-xl border border-slate-200/70">
            <div className="text-slate-500 font-medium">CUSUM Drift Weight</div>
            <div className="text-xl font-extrabold text-emerald-600 mt-1">20%</div>
          </div>
        </div>
      </div>
    </div>
  );
};
