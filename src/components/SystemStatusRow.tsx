import React from "react";
import { Cpu, Wifi, Database, Activity } from "lucide-react";

export interface SystemStatus {
  mode: "live" | "mock";
  rig: { online: boolean; last_seen_ts: number | null; detail: string };
  mqtt: { connected: boolean; detail: string };
  mongodb: { connected: boolean; telemetry_records: number | null; detail: string };
  pipeline: { receiving: boolean; detail: string };
  healthy: boolean;
  timestamp: number;
}

/**
 * Component status from /api/status — observed, not asserted.
 *
 * Previously these four cards were literal strings that read "Connected" even
 * with no broker running and no rig attached. A status panel that cannot report
 * a fault is worse than no status panel, so each card now derives its state and
 * says plainly when something is down.
 */
export const SystemStatusRow: React.FC<{ status?: SystemStatus | null }> = ({ status }) => {
  const unknown = !status;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5">
      <StatusCard
        title="ESP32 Rig"
        icon={<Cpu className="w-6 h-6" />}
        tone="blue"
        state={unknown ? "unknown" : status!.rig.online ? "ok" : status!.mode === "mock" ? "idle" : "down"}
        value={unknown ? "—" : status!.rig.online ? "Online" : status!.mode === "mock" ? "Mock Data" : "Offline"}
        detail={unknown ? "status unavailable" : status!.rig.detail}
      />

      <StatusCard
        title="MQTT Broker"
        icon={<Wifi className="w-6 h-6" />}
        tone="purple"
        state={unknown ? "unknown" : status!.mqtt.connected ? "ok" : status!.mode === "mock" ? "idle" : "down"}
        value={unknown ? "—" : status!.mqtt.connected ? "Connected" : "Not Connected"}
        detail={unknown ? "status unavailable" : status!.mqtt.detail}
      />

      <StatusCard
        title="MongoDB"
        icon={<Database className="w-6 h-6" />}
        tone="emerald"
        state={unknown ? "unknown" : status!.mongodb.connected ? "ok" : "down"}
        value={unknown ? "—" : status!.mongodb.connected ? "Connected" : "Unreachable"}
        detail={
          unknown
            ? "status unavailable"
            : status!.mongodb.connected && status!.mongodb.telemetry_records !== null
              ? `${status!.mongodb.telemetry_records.toLocaleString()} telemetry records`
              : status!.mongodb.detail
        }
      />

      <StatusCard
        title="Detection Pipeline"
        icon={<Activity className="w-6 h-6" />}
        tone="amber"
        state={unknown ? "unknown" : status!.pipeline.receiving ? "ok" : "down"}
        value={unknown ? "—" : status!.pipeline.receiving ? "Running" : "No Data"}
        detail={unknown ? "status unavailable" : status!.pipeline.detail}
      />
    </div>
  );
};

type State = "ok" | "idle" | "down" | "unknown";

const STATE_TEXT: Record<State, string> = {
  ok: "text-emerald-600",
  idle: "text-slate-500",
  down: "text-rose-600",
  unknown: "text-slate-400",
};

const STATE_DOT: Record<State, string> = {
  ok: "bg-emerald-500",
  idle: "bg-slate-400",
  down: "bg-rose-500",
  unknown: "bg-slate-300",
};

const ICON_TONES: Record<string, string> = {
  blue: "bg-blue-50 border-blue-100 text-blue-600",
  purple: "bg-purple-50 border-purple-100 text-purple-600",
  emerald: "bg-emerald-50 border-emerald-100 text-emerald-600",
  amber: "bg-amber-50 border-amber-100 text-amber-600",
};

const StatusCard: React.FC<{
  title: string; icon: React.ReactNode; tone: string;
  state: State; value: string; detail: string;
}> = ({ title, icon, tone, state, value, detail }) => (
  <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs flex items-center justify-between">
    <div className="space-y-1 min-w-0">
      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{title}</h3>
      <p className={`text-xl font-extrabold ${STATE_TEXT[state]}`}>{value}</p>
      <div className="flex items-center space-x-1.5 text-xs text-slate-500 font-medium pt-0.5">
        <span className={`w-2 h-2 rounded-full shrink-0 ${STATE_DOT[state]}`} />
        <span className="truncate">{detail}</span>
      </div>
    </div>
    <div className={`w-12 h-12 rounded-2xl border flex items-center justify-center shadow-2xs shrink-0 ${ICON_TONES[tone]}`}>
      {icon}
    </div>
  </div>
);
