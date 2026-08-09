import React from "react";
import { AlertTriangle, Bell, CheckCircle2, ShieldAlert } from "lucide-react";

interface AlertsViewProps { evaluation: any | null; }

export const AlertsView: React.FC<AlertsViewProps> = ({ evaluation }) => {
  const isAlarm = Boolean(evaluation?.is_alarm);
  const activeMethods: string[] = evaluation?.active_methods || [];
  const timestamp = evaluation?.ts ? new Date(evaluation.ts * 1000).toLocaleString() : null;

  return (
    <div className="space-y-6">
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="mb-6">
          <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2"><Bell className="w-6 h-6 text-blue-600" /><span>Verified Alert State</span></h2>
          <p className="text-xs text-slate-500 mt-1">The current fused decision and its contributing detector channels—no fabricated alert history.</p>
        </div>

        {isAlarm ? (
          <div className="rounded-2xl border border-rose-200 bg-rose-50 p-5">
            <div className="flex items-start justify-between gap-4">
              <div className="flex gap-3">
                <div className="w-10 h-10 rounded-xl bg-rose-600 text-white flex items-center justify-center"><ShieldAlert className="w-5 h-5" /></div>
                <div>
                  <h3 className="font-black text-rose-900">Probable leak · {Number(evaluation.likelihood_score || 0).toFixed(1)}% likelihood</h3>
                  <p className="text-xs text-rose-800 mt-1">{evaluation.evidence}</p>
                  <p className="text-[11px] text-rose-600 mt-2">{timestamp} · Zone {evaluation.zone || "pending"} · {evaluation.confidence_tier}</p>
                </div>
              </div>
              <span className="rounded-full bg-rose-600 px-3 py-1 text-[10px] font-black text-white">ACTIVE</span>
            </div>
          </div>
        ) : (
          <div className="rounded-2xl border border-emerald-200 bg-emerald-50 p-6 text-center">
            <CheckCircle2 className="w-9 h-9 mx-auto text-emerald-600" />
            <h3 className="mt-3 text-sm font-black text-emerald-900">No fused leak alert</h3>
            <p className="mt-1 text-xs text-emerald-700">{timestamp ? `Latest evaluated sample: ${timestamp}` : "Waiting for evaluated telemetry."}</p>
          </div>
        )}

        <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
          <div className="text-xs font-bold text-slate-800 flex items-center gap-2"><AlertTriangle className="w-4 h-4 text-amber-500" />Contributing channels</div>
          <p className="text-xs text-slate-500 mt-2">{activeMethods.length ? activeMethods.join(" · ") : "No detector channel is currently above its alarm threshold."}</p>
        </div>
        <p className="mt-4 text-[11px] text-slate-400">{evaluation?.false_positive_warning?.disclaimer || "Indicative result only; field verification is required."}</p>
      </div>
    </div>
  );
};
