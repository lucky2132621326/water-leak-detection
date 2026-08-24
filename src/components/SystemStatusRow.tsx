import React from "react";
import { Cpu, Activity, AlertTriangle } from "lucide-react";

export interface SystemStatus {
  mode: "live" | "mock";
  rig: { online: boolean; last_seen_ts: number | null; detail: string };
  mqtt: { connected: boolean; detail: string };
  mongodb: { connected: boolean; telemetry_records: number | null; detail: string };
  pipeline: { receiving: boolean; detail: string };
  publisher?: {
    expected_device_id: string | null;
    unexpected_device_ids: string[];
    duplicate_publisher_suspected: boolean;
    duplicate_packets: number;
    out_of_order_packets: number;
    dropped_estimate: number;
  };
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
  // A transient proxy error (502 during a backend restart, for example) can
  // return a body that parses as JSON but isn't a real status payload — guard
  // on the actual sub-objects, not just `status` being truthy, so a malformed
  // response degrades to "unknown" instead of crashing the whole dashboard.
  const unknown = !status || !status.rig || !status.mqtt || !status.mongodb || !status.pipeline;
  const publisher = status?.publisher;

  return (
    <>
      {publisher?.duplicate_publisher_suspected && (
        <div className="mb-5 rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 flex items-start gap-2.5">
          <AlertTriangle className="w-4 h-4 text-rose-600 shrink-0 mt-0.5" />
          <div className="text-xs text-rose-800">
            <div className="font-extrabold uppercase tracking-wide">Second publisher detected</div>
            <div className="font-medium opacity-90">
              Expected device <span className="font-mono">{publisher.expected_device_id}</span>, but also received
              telemetry claiming to be <span className="font-mono">{publisher.unexpected_device_ids.join(", ")}</span>.
              Something other than the real rig is publishing to rig/telemetry — check for a stray script or a second
              bridge instance before trusting these readings.
            </div>
          </div>
        </div>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
      <StatusCard
        title="ESP32 Rig"
        icon={<Cpu className="w-6 h-6" />}
        tone="blue"
        state={unknown ? "unknown" : status!.rig.online ? "ok" : status!.mode === "mock" ? "idle" : "down"}
        value={unknown ? "—" : status!.rig.online ? "Online" : status!.mode === "mock" ? "Test Bench" : "Offline"}
        detail={unknown ? "status unavailable" : status!.rig.detail}
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
    </>
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
