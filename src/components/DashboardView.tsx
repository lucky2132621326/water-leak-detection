import React from "react";
import {
  Cpu,
  Wifi,
  Database,
  Activity,
  Info,
  AlertTriangle,
  ChevronRight,
  Scale,
  Zap,
  TrendingUp,
  Gauge,
  Droplet,
  Power,
  ZapOff
} from "lucide-react";
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid
} from "recharts";
import { ImpactSummaryStrip } from "./ImpactSummaryStrip";
import type { SystemHealth, TelemetryEnvelope, TelemetrySample, ImpactSummary, SavingsSummary } from "../types";

const formatUptime = (seconds?: number | null) => {
  if (seconds == null) return "Awaiting device status";
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return `${days ? `${days}d ` : ""}${hours}h ${minutes}m uptime`;
};

const formatSampleTime = (ts?: number | null) => {
  if (!ts) return "No sample received";
  return new Date(ts * 1000).toLocaleString([], {
    month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit"
  });
};

// Custom Pump Graphic matching screenshot
const PumpGraphic = ({ label, isOn }: { label: string; isOn: boolean }) => (
  <div className="flex flex-col items-center shrink-0">
    <div className="relative w-16 h-12 flex items-center justify-center">
      <svg className="w-16 h-12" viewBox="0 0 64 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="2" y="20" width="10" height="8" rx="1" fill="#3B82F6" stroke="#1D4ED8" strokeWidth="1.5"/>
        <rect x="52" y="20" width="10" height="8" rx="1" fill="#3B82F6" stroke="#1D4ED8" strokeWidth="1.5"/>
        <rect x="10" y="16" width="3" height="16" rx="1" fill="#1D4ED8"/>
        <rect x="51" y="16" width="3" height="16" rx="1" fill="#1D4ED8"/>
        <circle cx="32" cy="24" r="16" fill="url(#pumpGrad)" stroke="#1D4ED8" strokeWidth="1.8"/>
        <circle cx="32" cy="24" r="10" fill="#2563EB"/>
        <circle cx="28" cy="20" r="4" fill="#60A5FA" opacity="0.6"/>
        <rect x="24" y="2" width="16" height="8" rx="2" fill="#3B82F6" stroke="#1D4ED8" strokeWidth="1.2"/>
        <line x1="28" y1="5" x2="36" y2="5" stroke="#DBEAFE" strokeWidth="1"/>
        <defs>
          <linearGradient id="pumpGrad" x1="16" y1="8" x2="48" y2="40" gradientUnits="userSpaceOnUse">
            <stop stopColor="#60A5FA"/>
            <stop offset="0.5" stopColor="#3B82F6"/>
            <stop offset="1" stopColor="#1E40AF"/>
          </linearGradient>
        </defs>
      </svg>
    </div>
    <span className="text-[11px] font-bold text-slate-800 uppercase tracking-tight mt-1">{label}</span>
    {isOn && (
      <span className="mt-1 px-2.5 py-0.5 rounded-full bg-emerald-100 text-emerald-700 text-[10px] font-extrabold uppercase tracking-wider">
        ON
      </span>
    )}
  </div>
);

// Custom 4-Port Flow Meter Valve Graphic matching screenshot
const FlowMeterGraphic = ({ name, code, value }: { name: string; code: string; value: string }) => (
  <div className="flex flex-col items-center shrink-0">
    <span className="text-[11px] font-bold text-slate-800">{name}</span>
    <span className="text-[11px] font-semibold text-slate-600">{code}</span>
    <div className="my-1.5 w-12 h-12 relative flex items-center justify-center">
      <svg className="w-12 h-12" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg">
        <rect x="21" y="2" width="6" height="6" rx="1" fill="#1D4ED8"/>
        <rect x="21" y="40" width="6" height="6" rx="1" fill="#1D4ED8"/>
        <rect x="2" y="21" width="6" height="6" rx="1" fill="#1D4ED8"/>
        <rect x="40" y="21" width="6" height="6" rx="1" fill="#1D4ED8"/>
        <rect x="22" y="6" width="4" height="36" fill="#2563EB"/>
        <rect x="6" y="22" width="36" height="4" fill="#2563EB"/>
        <circle cx="24" cy="24" r="14" fill="url(#valveGrad)" stroke="#1D4ED8" strokeWidth="1.8"/>
        <circle cx="24" cy="24" r="8" fill="#EFF6FF" stroke="#2563EB" strokeWidth="1.5"/>
        <circle cx="24" cy="24" r="3" fill="#2563EB"/>
        <defs>
          <linearGradient id="valveGrad" x1="10" y1="10" x2="38" y2="38" gradientUnits="userSpaceOnUse">
            <stop stopColor="#60A5FA"/>
            <stop offset="1" stopColor="#1E40AF"/>
          </linearGradient>
        </defs>
      </svg>
    </div>
    <span className="text-xs font-bold text-blue-600 font-mono">{value}</span>
  </div>
);

// Green Branch Valve / Tap Graphic matching screenshot
const GreenBranchValveGraphic = ({ value }: { value: string }) => (
  <div className="flex flex-col items-center">
    <span className="text-[11px] font-bold text-slate-800">Branch Flow</span>
    <span className="text-[11px] font-semibold text-slate-600">Qbranch</span>
    <span className="text-xs font-bold text-blue-600 font-mono my-0.5">{value}</span>
    <div className="w-8 h-8 flex items-center justify-center">
      <svg className="w-8 h-8" viewBox="0 0 32 32" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M16 6V20" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round"/>
        <path d="M10 12H22" stroke="#10B981" strokeWidth="2.5" strokeLinecap="round"/>
        <circle cx="16" cy="6" r="4" stroke="#10B981" strokeWidth="2" fill="#ECFDF5"/>
        <path d="M11 20L16 25L21 20Z" fill="#10B981"/>
      </svg>
    </div>
  </div>
);

interface DashboardViewProps {
  health?: SystemHealth | null;
  mode: "live" | "replay";
  latestTelemetry?: TelemetryEnvelope | null;
  telemetryHistory?: TelemetrySample[];
  onNavigateTab: (tab: any) => void;
  impact?: ImpactSummary | null;
  savings?: SavingsSummary | null;
  onAnalyzeImpact?: () => void;
  readOnly?: boolean;
}

export const DashboardView: React.FC<DashboardViewProps> = ({
  health,
  mode,
  latestTelemetry,
  telemetryHistory = [],
  onNavigateTab,
  impact,
  savings,
  onAnalyzeImpact,
  readOnly = false
}) => {
  const latest = latestTelemetry?.latest;
  const evaluation = latestTelemetry?.evaluation;
  const hasTelemetry = Boolean(latest);
  const qIn = latest?.q_in ?? 0;
  const qOut = latest?.q_out ?? 0;
  const qBranch = latest?.q_branch ?? 0;
  const residual = Number((latest?.residual ?? (qIn - (qOut + qBranch))).toFixed(3));
  const residualPercent = qIn > 0 ? Number(((residual / qIn) * 100).toFixed(2)) : 0;
  const currentAmp = Number(((latest?.current_ma ?? 0) / 1000).toFixed(2));
  const voltage = latest?.voltage_v ?? 0;
  const isLeak = Boolean(evaluation?.is_alarm);
  const isPump1On = latest?.pump1_on ?? latestTelemetry?.pump_on ?? false;
  const isPump2On = latest?.pump2_on ?? false;
  const likelihood = Number(evaluation?.likelihood_score ?? 0);
  const deviceOnline = Boolean(health?.device?.online);
  const replayReady = Boolean(health?.data_source_ready);

  const detectorRows = [
    { key: "mass_balance", label: "Mass Balance", icon: Scale, color: "bg-blue-600" },
    { key: "current_signature", label: "Current Signature", icon: Zap, color: "bg-purple-600" },
    { key: "cusum", label: "CUSUM Drift", icon: TrendingUp, color: "bg-emerald-500" },
    { key: "mnf", label: "Minimum Night Flow", icon: Activity, color: "bg-amber-500" },
  ].map((definition) => ({
    ...definition,
    result: evaluation?.detectors?.[definition.key],
  }));

  // Chart trend data points (Last 10 minutes)
  const chartData = telemetryHistory.length > 0 
    ? telemetryHistory.slice(-12).map((sample, idx) => {
        const timeObj = new Date(sample.ts * 1000);
        const timeLabel = timeObj.toLocaleTimeString("en-US", { hour12: false, hour: "2-digit", minute: "2-digit" });
        return {
          time: timeLabel || `10:${14 + idx * 2}`,
          Qin: sample.q_in ?? 0,
          Qout: sample.q_out ?? 0,
          Residual: sample.residual ?? 0
        };
      })
    : [];

  return (
    <div className="space-y-6">
      {/* 1. Top 4 System Status Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* Card 1: ESP32 Controller */}
        <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs flex items-center justify-between">
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">ESP32 Controller</h3>
            <p className={`text-xl font-extrabold ${deviceOnline ? "text-emerald-600" : "text-slate-500"}`}>
              {deviceOnline ? "Online" : mode === "replay" ? "Standby" : "Offline"}
            </p>
            <div className="flex items-center space-x-1.5 text-xs text-slate-500 font-medium pt-0.5">
              <span className={`w-2 h-2 rounded-full ${deviceOnline ? "bg-emerald-500" : "bg-slate-300"}`} />
              <span>{mode === "replay" && !deviceOnline ? "Hardware not required" : formatUptime(health?.device?.uptime_sec)}</span>
            </div>
          </div>
          <div className="w-12 h-12 rounded-2xl bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shadow-2xs">
            <Cpu className="w-6 h-6" />
          </div>
        </div>

        {/* Card 2: MQTT Broker */}
        <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs flex items-center justify-between">
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">MQTT Broker</h3>
            <p className={`text-xl font-extrabold ${health?.mqtt_connected ? "text-emerald-600" : "text-slate-500"}`}>
              {health?.mqtt_connected ? "Connected" : "Disconnected"}
            </p>
            <div className="flex items-center space-x-1.5 text-xs text-slate-500 font-medium pt-0.5">
              <span className={`w-2 h-2 rounded-full ${health?.mqtt_connected ? "bg-emerald-500" : "bg-slate-300"}`} />
              <span>{health?.mqtt_connected ? "Subscribed to rig/telemetry" : "Broker on port 1883 unavailable"}</span>
            </div>
          </div>
          <div className="w-12 h-12 rounded-2xl bg-purple-50 border border-purple-100 flex items-center justify-center text-purple-600 shadow-2xs">
            <Wifi className="w-6 h-6" />
          </div>
        </div>

        {/* Card 3: MongoDB */}
        <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs flex items-center justify-between">
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">MongoDB</h3>
            <p className={`text-xl font-extrabold ${health?.database_connected ? "text-emerald-600" : "text-rose-600"}`}>
              {health?.database_connected ? "Connected" : "Unavailable"}
            </p>
            <div className="flex items-center space-x-1.5 text-xs text-slate-500 font-medium pt-0.5">
              <Database className="w-3.5 h-3.5 text-emerald-600" />
              <span>Records: {(health?.telemetry_records ?? 0).toLocaleString()}</span>
            </div>
          </div>
          <div className="w-12 h-12 rounded-2xl bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600 shadow-2xs">
            <Database className="w-6 h-6" />
          </div>
        </div>

        {/* Card 4: System Health */}
        <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs flex items-center justify-between">
          <div className="space-y-1">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">System Health</h3>
            <p className={`text-xl font-extrabold ${health?.status === "ok" ? "text-emerald-600" : "text-amber-600"}`}>
              {health?.status === "ok" ? "Operational" : "Degraded"}
            </p>
            <p className="text-xs text-slate-500 font-medium pt-0.5">
              {mode === "replay" ? (replayReady ? "Replay pipeline verified" : "No replay sample") : (deviceOnline ? "Live telemetry verified" : "Waiting for ESP32")}
            </p>
          </div>
          <div className="w-12 h-12 rounded-2xl bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600 shadow-2xs">
            <Activity className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* 1b. Impact strip — translates the current leak rate into litres, rupees
             and a severity category, plus the cumulative savings KPI. */}
      <ImpactSummaryStrip impact={impact} savings={savings} onAnalyzeImpact={onAnalyzeImpact} />

      {/* 2. Middle Grid: System Overview (65%) & Active Exp + Detector Status (35%) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (8 cols): System Overview Hydraulic Rig Diagram */}
        <div className="lg:col-span-8 bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs flex flex-col justify-between">
          <div>
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-slate-900 tracking-tight">System Overview</h2>
              <button className="text-slate-400 hover:text-slate-600 transition" title="System Specifications">
                <Info className="w-5 h-5 stroke-[1.5]" />
              </button>
            </div>

            {/* Visual Hydraulic Pipe Network Graphic */}
            <div className="relative py-8 px-4 bg-white rounded-2xl flex items-center justify-between my-2 overflow-x-auto min-h-[260px] select-none">
              {/* PUMP 1 */}
              <PumpGraphic label="PUMP 1" isOn={isPump1On} />

              {/* Arrow -> */}
              <div className="flex items-center text-slate-400 font-bold px-1 shrink-0">
                <svg className="w-8 h-4 text-slate-600" viewBox="0 0 32 16" fill="none">
                  <line x1="0" y1="8" x2="24" y2="8" stroke="currentColor" strokeWidth="2"/>
                  <path d="M20 4L28 8L20 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>

              {/* Flow 1 */}
              <FlowMeterGraphic name="Flow 1" code="Qin" value={`${qIn} L/min`} />

              {/* Middle Pipe Junction with Branch Flow & Servo Valve */}
              <div className="relative flex-1 max-w-[220px] h-32 flex items-center justify-center mx-2 shrink-0">
                {/* SVG Piping Network */}
                <svg className="absolute inset-0 w-full h-full" viewBox="0 0 220 128" fill="none">
                  {/* Main Horizontal Pipe */}
                  <line x1="0" y1="64" x2="220" y2="64" stroke="#1E293B" strokeWidth="2.5"/>
                  
                  {/* Upward Curved Branch to Green Valve */}
                  <path d="M110 64 C 110 50, 110 32, 110 24" stroke="#1E293B" strokeWidth="2.5" fill="none"/>
                  
                  {/* Downward Curved Branch to Servo Valve */}
                  <path d="M110 64 C 110 78, 110 90, 110 102" stroke="#1E293B" strokeWidth="2.5" fill="none"/>
                  <polygon points="104,100 110,110 116,100" fill="#1E293B"/>
                </svg>

                {/* Top Label: Branch Flow */}
                <div className="absolute -top-7 left-1/2 -translate-x-1/2 z-10">
                  <GreenBranchValveGraphic value={`${qBranch} L/min`} />
                </div>

                {/* Bottom Label: SERVO VALVE */}
                <div className="absolute -bottom-6 left-1/2 -translate-x-1/2 z-10 flex flex-col items-center">
                  <span className="text-[11px] font-bold text-slate-800 uppercase tracking-tight">SERVO VALVE</span>
                  <span className={`text-xs font-semibold ${(latest?.servo_deg ?? 0) > 0 ? "text-rose-600" : "text-emerald-600"}`}>
                    {(latest?.servo_deg ?? 0) > 0 ? `Aperture ${latest?.servo_deg}°` : "Sealed (0°)"}
                  </span>
                </div>
              </div>

              {/* Flow 2 */}
              <FlowMeterGraphic name="Flow 2" code="Qout" value={`${qOut} L/min`} />

              {/* Arrow -> */}
              <div className="flex items-center text-slate-400 font-bold px-1 shrink-0">
                <svg className="w-8 h-4 text-slate-600" viewBox="0 0 32 16" fill="none">
                  <line x1="0" y1="8" x2="24" y2="8" stroke="currentColor" strokeWidth="2"/>
                  <path d="M20 4L28 8L20 12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
              </div>

              <PumpGraphic label="PUMP 2" isOn={isPump2On} />
            </div>
          </div>

          {/* Bottom Residual Summary Cards inside System Overview */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mt-6">
            <div className="bg-slate-50/80 border border-slate-200/80 rounded-2xl p-4 flex items-center justify-between shadow-2xs">
              <span className="text-xs sm:text-sm font-bold text-slate-900">Bias-corrected residual</span>
              <span className={`text-lg sm:text-xl font-extrabold ${Math.abs(residual) > 0.2 ? "text-rose-600" : "text-emerald-600"}`}>{residual} L/min</span>
            </div>
            <div className="bg-slate-50/80 border border-slate-200/80 rounded-2xl p-4 flex items-center justify-between shadow-2xs">
              <span className="text-xs sm:text-sm font-bold text-slate-900">Residual %</span>
              <span className={`text-lg sm:text-xl font-extrabold ${Math.abs(residualPercent) > 5 ? "text-rose-600" : "text-emerald-600"}`}>{residualPercent.toFixed(2)}%</span>
            </div>
          </div>
        </div>

        {/* Right Column (4 cols): Active Experiment & Detector Status Stack */}
        <div className="lg:col-span-4 space-y-6">
          {/* Active Experiment Card */}
          <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs">
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-bold text-slate-900 tracking-tight">Active Data Session</h3>
              {!readOnly && (
                <button
                  onClick={() => onNavigateTab("experiment-control")}
                  className="text-xs font-bold text-blue-600 hover:text-blue-700 transition"
                >
                  View All
                </button>
              )}
            </div>

            <div className="space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-[11px] text-slate-400 font-medium">Source identity</div>
                  <div className="text-sm font-extrabold text-slate-900 font-mono">
                    {mode === "replay" ? (health?.replay_run_id || "NO_RUN") : (latest?.device_id || health?.device?.device_id || "NO_DEVICE")}
                  </div>
                </div>
                <span className={`px-3 py-1 rounded-full text-[11px] font-bold ${hasTelemetry ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-600"}`}>
                  {hasTelemetry ? (mode === "replay" ? "REPLAYING" : "STREAMING") : "WAITING"}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2 text-xs pt-1 border-t border-slate-100">
                <div>
                  <span className="text-slate-400 block text-[11px]">Latest sample</span>
                  <span className="font-semibold text-slate-800">{formatSampleTime(latest?.ts)}</span>
                </div>
                <div>
                  <span className="text-slate-400 block text-[11px]">Evidence window</span>
                  <span className="font-semibold text-slate-800">
                    {evaluation?.time_window ? `${evaluation.time_window.duration_sec}s` : `${telemetryHistory.length} samples`}
                  </span>
                </div>
              </div>

              {/* Red Leak Alarm Banner */}
              <div 
                onClick={() => onNavigateTab("leak-detection")}
                className={`${isLeak ? "bg-rose-600 hover:bg-rose-700 text-white shadow-rose-600/20" : "bg-emerald-50 hover:bg-emerald-100 text-emerald-800 border border-emerald-200"} p-3.5 rounded-2xl flex items-center justify-between cursor-pointer transition shadow-md`}
              >
                <div className="flex items-center space-x-3">
                    <div className={`w-8 h-8 rounded-full flex items-center justify-center shrink-0 ${isLeak ? "bg-white/20" : "bg-emerald-100"}`}>
                      <AlertTriangle className={`w-5 h-5 ${isLeak ? "text-white" : "text-emerald-700"}`} />
                  </div>
                  <div>
                    <div className="text-xs font-black tracking-wide uppercase">{isLeak ? "LEAK LIKELY" : "NO CONFIRMED LEAK"}</div>
                    <div className={`text-xs font-semibold ${isLeak ? "text-rose-100" : "text-emerald-700"}`}>
                      Likelihood: {likelihood.toFixed(1)}% · {evaluation?.confidence_tier || "NONE"}
                    </div>
                  </div>
                </div>
                <ChevronRight className={`w-5 h-5 ${isLeak ? "text-white/80" : "text-emerald-600"}`} />
              </div>
            </div>
          </div>

          {/* Detector Status Card */}
          <div className="bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-slate-900 tracking-tight">Detector Status</h3>
              <button 
                onClick={() => onNavigateTab("leak-detection")}
                className="text-xs font-bold text-blue-600 hover:text-blue-700 transition"
              >
                View All
              </button>
            </div>

            <div className="space-y-4">
              {detectorRows.map(({ key, label, icon: Icon, color, result }) => {
                const confidence = Math.max(0, Math.min(100, Number(result?.confidence ?? 0) * 100));
                const alarm = Boolean(result?.is_alarm);
                return (
                  <div key={key} className="space-y-1.5">
                    <div className="flex items-center justify-between text-xs gap-3">
                      <div className="flex items-center space-x-2 min-w-0">
                        <Icon className="w-4 h-4 text-slate-600 shrink-0" />
                        <span className="font-semibold text-slate-800 truncate">{label}</span>
                      </div>
                      <div className="flex items-center space-x-2 shrink-0">
                        <span className="font-bold text-slate-900">{confidence.toFixed(0)}%</span>
                        <span className={`px-2 py-0.5 rounded-md text-[10px] font-extrabold uppercase ${alarm ? "bg-rose-100 text-rose-700" : "bg-emerald-100 text-emerald-700"}`}>
                          {alarm ? "ALERT" : "NORMAL"}
                        </span>
                      </div>
                    </div>
                    <div className="w-full h-2 rounded-full bg-slate-100 overflow-hidden">
                      <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${confidence}%` }} />
                    </div>
                  </div>
                );
              })}
              {!evaluation && <p className="text-xs text-slate-400">Waiting for the first evaluated sample.</p>}
            </div>
          </div>
        </div>
      </div>

      {/* 3. Bottom Grid Row (3 Columns: Telemetry Summary (25%), Trend Chart (45%), Alerts (30%)) */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column (3 cols): Live Telemetry Summary */}
        <div className="lg:col-span-3 bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs space-y-4">
          <h3 className="text-sm font-bold text-slate-900 tracking-tight flex items-center space-x-2">
            <Activity className="w-4 h-4 text-blue-600" />
            <span>{mode === "live" ? "Live" : "Replay"} Telemetry Summary</span>
          </h3>

          <div className="space-y-3.5 divide-y divide-slate-100 text-xs">
            <div className="flex items-center justify-between pt-1">
              <div className="flex items-center space-x-2 text-slate-600">
                <Scale className="w-4 h-4 text-blue-500" />
                <span className="font-medium">Qin (Flow 1)</span>
              </div>
              <span className="font-bold text-blue-600 text-sm">{qIn} L/min</span>
            </div>

            <div className="flex items-center justify-between pt-2.5">
              <div className="flex items-center space-x-2 text-slate-600">
                <Gauge className="w-4 h-4 text-emerald-500" />
                <span className="font-medium">Qout (Flow 2)</span>
              </div>
              <span className="font-bold text-blue-600 text-sm">{qOut} L/min</span>
            </div>

            <div className="flex items-center justify-between pt-2.5">
              <div className="flex items-center space-x-2 text-slate-600">
                <Droplet className="w-4 h-4 text-indigo-500" />
                <span className="font-medium">Qbranch (Flow 3)</span>
              </div>
              <span className="font-bold text-blue-600 text-sm">{qBranch} L/min</span>
            </div>

            <div className="flex items-center justify-between pt-2.5">
              <div className="flex items-center space-x-2 text-slate-600">
                <Zap className="w-4 h-4 text-purple-500" />
                <span className="font-medium">Pump Current</span>
              </div>
              <span className="font-bold text-purple-600 text-sm">{currentAmp} A</span>
            </div>

            <div className="flex items-center justify-between pt-2.5">
              <div className="flex items-center space-x-2 text-slate-600">
                <ZapOff className="w-4 h-4 text-amber-500" />
                <span className="font-medium">Voltage</span>
              </div>
              <span className="font-bold text-amber-600 text-sm">{voltage} V</span>
            </div>
          </div>
        </div>

        {/* Center Column (5 cols): Telemetry Trend (Last 10 Minutes) */}
        <div className="lg:col-span-5 bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs flex flex-col justify-between">
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">Telemetry Trend (Last 10 Minutes)</h3>
            <div className="flex items-center space-x-3 text-xs font-medium">
              <span className="flex items-center space-x-1 text-blue-600">
                <span className="w-2.5 h-2.5 rounded-full bg-blue-600 inline-block" />
                <span>Qin</span>
              </span>
              <span className="flex items-center space-x-1 text-emerald-600">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
                <span>Qout</span>
              </span>
              <span className="flex items-center space-x-1 text-rose-600">
                <span className="w-2.5 h-2.5 rounded-full bg-rose-500 inline-block" />
                <span>Residual</span>
              </span>
            </div>
          </div>

          <div className="h-48 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#F1F5F9" />
                <XAxis dataKey="time" stroke="#94A3B8" fontSize={11} tickLine={false} />
                <YAxis stroke="#94A3B8" fontSize={11} tickLine={false} domain={["auto", "auto"]} />
                <Tooltip 
                  contentStyle={{ backgroundColor: "#FFFFFF", borderColor: "#E2E8F0", borderRadius: "12px", fontSize: "12px" }} 
                />
                <Line type="monotone" dataKey="Qin" stroke="#2563EB" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="Qout" stroke="#10B981" strokeWidth={2.5} dot={false} />
                <Line type="monotone" dataKey="Residual" stroke="#EF4444" strokeWidth={2.5} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Right Column (4 cols): Recent Alerts */}
        <div className="lg:col-span-4 bg-white rounded-2xl border border-slate-200/80 p-5 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <h3 className="text-sm font-bold text-slate-900 tracking-tight">Recent Alerts</h3>
            <button 
              onClick={() => onNavigateTab("alerts")}
              className="text-xs font-bold text-blue-600 hover:text-blue-700 transition"
            >
              View All
            </button>
          </div>

          <div className="space-y-3.5">
            {isLeak ? (
              <>
                <div
                  onClick={() => onNavigateTab("leak-detection")}
                  className="flex items-center justify-between p-2.5 rounded-xl hover:bg-rose-50 transition cursor-pointer border border-rose-100"
                >
                  <div className="flex items-start space-x-3 min-w-0">
                    <span className="w-2.5 h-2.5 rounded-full bg-rose-500 mt-1 shrink-0" />
                    <div className="min-w-0">
                      <div className="text-xs font-bold text-slate-800">Leak likelihood {likelihood.toFixed(1)}% · {evaluation?.zone || "zone pending"}</div>
                      <div className="text-[11px] text-slate-400">{formatSampleTime(latest?.ts)}</div>
                    </div>
                  </div>
                  <ChevronRight className="w-4 h-4 text-slate-400 shrink-0" />
                </div>
                <div className="p-2.5 rounded-xl bg-amber-50 border border-amber-100">
                  <div className="text-xs font-bold text-amber-900">Evidence</div>
                  <div className="text-[11px] text-amber-800 mt-1 leading-relaxed">{evaluation?.evidence || "Detector evidence is being assembled."}</div>
                </div>
              </>
            ) : (
              <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-100">
                <div className="text-xs font-bold text-emerald-800">No active leak alert</div>
                <div className="text-[11px] text-emerald-700 mt-1">
                  {hasTelemetry ? `Latest sample evaluated ${formatSampleTime(latest?.ts)}.` : "Waiting for telemetry before evaluating the network."}
                </div>
              </div>
            )}
            <p className="text-[10px] leading-relaxed text-slate-400">
              Indicative decision support only. Field verification is required before repair action.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
