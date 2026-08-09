import React from "react";
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, CartesianGrid, Legend } from "recharts";
import { Radio, ShieldCheck, Waves } from "lucide-react";
import type { SystemHealth, TelemetryEnvelope, TelemetrySample } from "../types";

interface LiveMonitorViewProps {
  telemetryHistory: TelemetrySample[];
  latestTelemetry: TelemetryEnvelope | null;
  mode: "live" | "replay";
  health: SystemHealth | null;
}

export const LiveMonitorView: React.FC<LiveMonitorViewProps> = ({
  telemetryHistory,
  latestTelemetry,
  mode,
  health,
}) => {
  const latest = latestTelemetry?.latest;

  const chartData = telemetryHistory.map((item) => ({
    time: new Date(item.ts * 1000).toLocaleTimeString([], { hour12: false, minute: '2-digit', second: '2-digit' }),
    Qin: item.q_in,
    Qout: item.q_out,
    Residual: item.residual,
    CurrentMA: item.current_ma
  }));

  return (
    <div className="space-y-6">
      {/* Source and safety banner */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
              <Waves className="w-6 h-6 text-blue-600" />
              <span>Telemetry Observatory</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              One canonical 1 Hz stream for both ESP32 hardware telemetry and deterministic replay evidence.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5 text-xs font-bold">
            <span className={`px-3 py-2 rounded-xl border flex items-center gap-2 ${mode === "live" ? "bg-rose-50 border-rose-200 text-rose-700" : "bg-indigo-50 border-indigo-200 text-indigo-700"}`}>
              <Radio className="w-4 h-4" /> {mode === "live" ? "LIVE ESP32" : `REPLAY ${health?.replay_run_id || ""}`}
            </span>
            <span className="px-3 py-2 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-700 flex items-center gap-2">
              <ShieldCheck className="w-4 h-4" /> Read-only safety boundary
            </span>
          </div>
        </div>
      </div>

      {/* Metric Cards Grid */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-5">
        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Inlet Flow (Q_in)</div>
          <div className="text-3xl font-extrabold text-blue-600 mt-2">{latest?.q_in ?? "0.00"} <span className="text-sm font-semibold text-slate-400">L/min</span></div>
          <div className="text-[11px] font-medium text-slate-400 mt-1">YF-S201 Sensor 1 (K=456)</div>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Outlet Flow (Q_out)</div>
          <div className="text-3xl font-extrabold text-cyan-600 mt-2">{latest?.q_out ?? "0.00"} <span className="text-sm font-semibold text-slate-400">L/min</span></div>
          <div className="text-[11px] font-medium text-slate-400 mt-1">YF-S201 Sensor 2 (K=448)</div>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Mass Residual (ΔQ)</div>
          <div className={`text-3xl font-black mt-2 ${
            (latest?.residual ?? 0) > 0.3 ? "text-rose-600 animate-pulse" : "text-emerald-600"
          }`}>
            {latest?.residual ?? "0.00"} <span className="text-sm font-semibold text-slate-400">L/min</span>
          </div>
          <div className="text-[11px] font-medium text-slate-400 mt-1">Q_in - (Q_out + Q_branch)</div>
        </div>

        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
          <div className="text-xs font-bold text-slate-500 uppercase tracking-wider">Pump Load Current (I_mA)</div>
          <div className="text-3xl font-extrabold text-amber-600 mt-2">{latest?.current_ma ?? "0.0"} <span className="text-sm font-semibold text-slate-400">mA</span></div>
          <div className="text-[11px] font-medium text-slate-400 mt-1">INA219 High-Side Sensor</div>
        </div>
      </div>

      {/* Live Charts */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Flow Rates Chart */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
          <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center justify-between">
            <span>Flow Telemetry (Q_in vs Q_out)</span>
            <span className="text-xs text-slate-400 font-mono font-medium">1Hz Stream</span>
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="time" stroke="#94A3B8" tick={{ fontSize: 11 }} />
                <YAxis stroke="#94A3B8" domain={[0, 7]} tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0', borderRadius: '12px', color: '#0F172A', fontSize: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)' }} />
                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                <Line type="monotone" dataKey="Qin" name="Qin (Inlet)" stroke="#2563EB" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="Qout" name="Qout (Outlet)" stroke="#0891B2" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="Residual" name="Mass Differential ΔQ" stroke="#E11D48" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Pump Current & Pressure Chart */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-5 shadow-xs">
          <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center justify-between">
            <span>Pump Motor Load Current (I_mA)</span>
            <span className="text-xs text-slate-400 font-mono font-medium">INA219 Telemetry</span>
          </h3>
          <div className="h-64">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="time" stroke="#94A3B8" tick={{ fontSize: 11 }} />
                <YAxis stroke="#94A3B8" domain={[350, 450]} tick={{ fontSize: 11 }} />
                <Tooltip contentStyle={{ backgroundColor: '#FFFFFF', borderColor: '#E2E8F0', borderRadius: '12px', color: '#0F172A', fontSize: '12px', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.05)' }} />
                <Legend wrapperStyle={{ fontSize: '12px', paddingTop: '10px' }} />
                <Line type="monotone" dataKey="CurrentMA" name="Current (mA)" stroke="#D97706" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  );
};
