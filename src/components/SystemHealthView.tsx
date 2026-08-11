import React, { useState } from "react";
import { Cpu, Server, Database, Activity, HardDrive, Terminal } from "lucide-react";

export const SystemHealthView: React.FC = () => {
  const [logFilter, setLogFilter] = useState<"ALL" | "INFO" | "WARNING" | "ERROR">("ALL");

  const logs = [
    { time: "14:52:10", level: "INFO", message: "[MQTT Collector] Received 1Hz payload from rig/telemetry (seq=1042, q_in=5.20 LPM, q_out=5.18 LPM)" },
    { time: "14:52:09", level: "INFO", message: "[MongoDB Engine] Executed query on collection `telemetry` with ts index scan (0.1ms)" },
    { time: "14:52:05", level: "INFO", message: "[Mass Balance] Residual ΔQ = 0.02 LPM within 3-sigma bound (threshold=0.25 LPM)" },
    { time: "14:51:50", level: "WARNING", message: "[Calibration] Mild pump current ripple detected (I = 422 mA, noise std=0.03)" },
    { time: "14:50:30", level: "INFO", message: "[CP-SAT Scheduler] Work Order WO-2026-001 optimization route computed (solver status: OPTIMAL)" },
    { time: "14:48:12", level: "ERROR", message: "[Simulated Anomaly] Trapped air bubble detected in clear PVC tube — auto-filtered by EWMA" },
  ];

  const filteredLogs = logFilter === "ALL" ? logs : logs.filter((l) => l.level === logFilter);

  return (
    <div className="space-y-6">
      {/* Banner */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
          <Activity className="w-6 h-6 text-blue-600" />
          <span>System Health, Hardware Status & Diagnostic Logs</span>
        </h2>
        <p className="text-xs text-slate-500 mt-1">
          Real-time diagnostics for physical rig microcontroller, MQTT broker socket connections, MongoDB indexes, and process resources.
        </p>
      </div>

      {/* Hardware Status Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        {/* ESP32 Status Card */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Cpu className="w-5 h-5 text-blue-600" />
              <h3 className="text-sm font-bold text-slate-900">ESP32 DevKit V1</h3>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 font-mono">
              ONLINE
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between text-slate-500 font-medium">
              <span>IP Address:</span>
              <span className="text-slate-900 font-bold">192.168.1.104</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Firmware:</span>
              <span className="text-slate-900 font-bold">v1.2.0-esp32</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Free Heap:</span>
              <span className="text-slate-900 font-bold">184 KB</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>WiFi RSSI:</span>
              <span className="text-emerald-600 font-bold">-58 dBm (Strong)</span>
            </div>
          </div>
        </div>

        {/* MQTT Broker Card */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Server className="w-5 h-5 text-purple-600" />
              <h3 className="text-sm font-bold text-slate-900">MQTT Broker (Mosquitto)</h3>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 font-mono">
              CONNECTED
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Broker Port:</span>
              <span className="text-slate-900 font-bold">1883</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Active Topic:</span>
              <span className="text-purple-600 font-bold">rig/telemetry</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Publish Rate:</span>
              <span className="text-slate-900 font-bold">1.0 Hz</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Packet Loss:</span>
              <span className="text-emerald-600 font-bold">0.00%</span>
            </div>
          </div>
        </div>

        {/* MongoDB Engine Card */}
        <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center space-x-2">
              <Database className="w-5 h-5 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900">MongoDB Engine</h3>
            </div>
            <span className="px-2.5 py-0.5 rounded-full text-[10px] font-bold bg-emerald-100 text-emerald-800 border border-emerald-200 font-mono">
              HEALTHY
            </span>
          </div>

          <div className="space-y-2 text-xs font-mono">
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Database Name:</span>
              <span className="text-emerald-700 font-bold">Mode-scoped MongoDB</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Collections:</span>
              <span className="text-slate-900 font-bold">5 active</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Indexes:</span>
              <span className="text-slate-900 font-bold">`ts`, `is_alarm`, `id`</span>
            </div>
            <div className="flex justify-between text-slate-500 font-medium">
              <span>Uptime:</span>
              <span className="text-slate-900 font-bold">99.98%</span>
            </div>
          </div>
        </div>
      </div>

      {/* Resource Usage Bars */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 mb-4 flex items-center space-x-2">
          <HardDrive className="w-4 h-4 text-cyan-600" />
          <span>Container Resource Usage</span>
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <div>
            <div className="flex justify-between text-xs font-bold text-slate-600 mb-1.5">
              <span>CPU Utilization</span>
              <span className="text-cyan-700 font-mono font-extrabold">12%</span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden border border-slate-200/60">
              <div className="bg-cyan-500 h-2.5 rounded-full" style={{ width: "12%" }}></div>
            </div>
          </div>

          <div>
            <div className="flex justify-between text-xs font-bold text-slate-600 mb-1.5">
              <span>RAM Allocation</span>
              <span className="text-purple-700 font-mono font-extrabold">245 MB / 1024 MB</span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden border border-slate-200/60">
              <div className="bg-purple-500 h-2.5 rounded-full" style={{ width: "24%" }}></div>
            </div>
          </div>

          <div>
            <div className="flex justify-between text-xs font-bold text-slate-600 mb-1.5">
              <span>Storage Usage</span>
              <span className="text-emerald-700 font-mono font-extrabold">1.2 GB / 20 GB</span>
            </div>
            <div className="w-full bg-slate-100 rounded-full h-2.5 overflow-hidden border border-slate-200/60">
              <div className="bg-emerald-500 h-2.5 rounded-full" style={{ width: "6%" }}></div>
            </div>
          </div>
        </div>
      </div>

      {/* Log Viewer */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <Terminal className="w-4 h-4 text-slate-700" />
            <span>Real-time System & Detector Logs</span>
          </h3>

          <div className="flex items-center space-x-1.5 bg-slate-100 p-1 rounded-xl border border-slate-200">
            {(["ALL", "INFO", "WARNING", "ERROR"] as const).map((lvl) => (
              <button
                key={lvl}
                onClick={() => setLogFilter(lvl)}
                className={`px-3 py-1 rounded-lg text-[10px] font-bold font-mono transition ${
                  logFilter === lvl ? "bg-blue-600 text-white shadow-2xs" : "text-slate-600 hover:text-slate-900"
                }`}
              >
                {lvl}
              </button>
            ))}
          </div>
        </div>

        <div className="bg-slate-950 rounded-xl p-4 font-mono text-xs text-slate-200 space-y-2 border border-slate-800 max-h-64 overflow-y-auto shadow-inner">
          {filteredLogs.map((l, idx) => (
            <div key={idx} className="flex items-start space-x-3 hover:bg-slate-900/80 p-1 rounded transition">
              <span className="text-slate-500 shrink-0">{l.time}</span>
              <span className={`px-1.5 py-0.2 rounded text-[9px] font-bold shrink-0 ${
                l.level === "INFO" ? "bg-blue-500/20 text-blue-300" :
                l.level === "WARNING" ? "bg-amber-500/20 text-amber-300" :
                "bg-rose-500/20 text-rose-300"
              }`}>
                {l.level}
              </span>
              <span className="text-slate-300 break-all">{l.message}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
};
