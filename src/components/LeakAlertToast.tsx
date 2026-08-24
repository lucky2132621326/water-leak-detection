import React from "react";
import { AlertTriangle, Bell, X } from "lucide-react";

import type { LeakAlert } from "../types";

interface LeakAlertToastProps {
  alert: LeakAlert;
  onOpen: () => void;
  onDismiss: () => void;
}

export const LeakAlertToast: React.FC<LeakAlertToastProps> = ({ alert, onOpen, onDismiss }) => (
  <div
    role="alert"
    aria-live="assertive"
    className="fixed right-6 top-24 z-50 w-[min(26rem,calc(100vw-3rem))] overflow-hidden rounded-2xl border border-rose-300 bg-white shadow-2xl shadow-rose-950/20"
  >
    <div className="flex items-start gap-3 bg-rose-600 px-4 py-3 text-white">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
      <div className="min-w-0 flex-1">
        <p className="text-sm font-extrabold tracking-wide">LEAK DETECTED</p>
        <p className="mt-0.5 text-[11px] font-semibold text-rose-100">
          {alert.source === "live" ? "Live Sensors" : "Mock Scenario"} · {alert.alert_id}
        </p>
      </div>
      <button
        type="button"
        aria-label="Dismiss leak notification"
        onClick={onDismiss}
        className="rounded-lg p-1 text-rose-100 transition hover:bg-white/15 hover:text-white"
      >
        <X className="h-4 w-4" />
      </button>
    </div>

    <div className="space-y-2 px-4 py-4 text-xs text-slate-600">
      <div className="flex items-center justify-between gap-4">
        <span className="font-semibold text-slate-500">Location</span>
        <span className="font-extrabold text-slate-900">{alert.zone}</span>
      </div>
      <div className="flex items-center justify-between gap-4">
        <span className="font-semibold text-slate-500">Estimated leak</span>
        <span className="font-extrabold text-rose-600">
          {Number(alert.peak_leak_rate_lpm ?? alert.leak_rate_lpm ?? 0).toFixed(3)} L/min
        </span>
      </div>
      <div className="flex items-center justify-between gap-4">
        <span className="font-semibold text-slate-500">Confidence</span>
        <span className="font-extrabold text-slate-900">
          {alert.confidence_tier} ({Number(alert.likelihood_score ?? 0).toFixed(1)}%)
        </span>
      </div>

      <button
        type="button"
        onClick={onOpen}
        className="mt-2 flex w-full items-center justify-center gap-2 rounded-xl bg-slate-900 px-3 py-2.5 font-bold text-white transition hover:bg-slate-800"
      >
        <Bell className="h-4 w-4" />
        <span>Open Alert Center</span>
      </button>
    </div>
  </div>
);
