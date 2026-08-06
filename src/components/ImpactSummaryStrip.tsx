import React from "react";
import { Droplets, IndianRupee, ShieldAlert, TrendingUp, ArrowRight } from "lucide-react";
import type { ImpactSummary, SavingsSummary } from "../types";
import { formatLitres, formatMoney, formatRate, severityStyle, urgencyStyle } from "../lib/impact";

interface Props {
  impact?: ImpactSummary | null;
  savings?: SavingsSummary | null;
  onAnalyzeImpact?: () => void;
}

/**
 * The "so what?" row: translates the detector's current leak rate into litres,
 * rupees and a severity category, alongside the cumulative savings KPI.
 * Rendered on the Dashboard directly beneath the system-status cards.
 */
export const ImpactSummaryStrip: React.FC<Props> = ({ impact, savings, onAnalyzeImpact }) => {
  const rate = impact?.leak_rate_lpm ?? 0;
  const symbol = impact?.currency_symbol ?? "₹";
  const sev = severityStyle(impact?.severity);
  const urg = urgencyStyle(impact?.urgency);
  const hasLoss = rate > 0;

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-5">
      {/* Water loss */}
      <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Water Loss</h3>
            <p className="text-2xl font-extrabold text-slate-900 mt-1 tracking-tight">
              {formatLitres(impact?.litres_per_day, { compact: true })}
              <span className="text-sm font-bold text-slate-400 ml-1">/day</span>
            </p>
            <p className="text-xs text-slate-500 font-medium mt-1">
              {formatRate(rate)} · {formatLitres(impact?.litres_per_month, { compact: true })}/month
            </p>
          </div>
          <div className="w-11 h-11 rounded-2xl bg-blue-50 border border-blue-100 flex items-center justify-center text-blue-600 shrink-0">
            <Droplets className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Cost */}
      <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Annual Cost</h3>
            <p className={`text-2xl font-extrabold mt-1 tracking-tight ${hasLoss ? "text-rose-600" : "text-emerald-600"}`}>
              {formatMoney(impact?.cost_per_year, symbol, { compact: true })}
            </p>
            <p className="text-xs text-slate-500 font-medium mt-1">
              {formatMoney(impact?.cost_per_day, symbol)}/day · {formatMoney(impact?.cost_per_month, symbol, { compact: true })}/month
            </p>
          </div>
          <div className="w-11 h-11 rounded-2xl bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600 shrink-0">
            <IndianRupee className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Severity */}
      <div className={`bg-white rounded-2xl p-5 border shadow-xs ${hasLoss ? sev.ring : "border-slate-200/80"}`}>
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Severity</h3>
            <div className="flex items-center space-x-2 mt-1.5">
              <span className="text-lg leading-none">{sev.emoji}</span>
              <span className={`px-2.5 py-1 rounded-lg text-sm font-extrabold border ${sev.badge}`}>
                {impact?.severity ?? "NONE"}
              </span>
            </div>
            <span className={`inline-block mt-2 px-2 py-0.5 rounded-md text-[10px] font-extrabold border ${urg.badge}`}>
              {impact?.urgency ?? "NONE"}
            </span>
          </div>
          <div className="w-11 h-11 rounded-2xl bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600 shrink-0">
            <ShieldAlert className="w-5 h-5" />
          </div>
        </div>
      </div>

      {/* Savings counter */}
      <div className="bg-gradient-to-br from-emerald-600 to-teal-700 rounded-2xl p-5 border border-emerald-700 shadow-sm text-white">
        <div className="flex items-start justify-between">
          <div className="min-w-0">
            <h3 className="text-xs font-semibold text-emerald-100 uppercase tracking-wider">Water Saved</h3>
            <p className="text-2xl font-extrabold mt-1 tracking-tight">
              {formatLitres(savings?.water_saved_litres, { compact: true })}
            </p>
            <p className="text-xs text-emerald-100/90 font-medium mt-1">
              {savings?.leaks_prevented ?? 0} leaks repaired · {formatMoney(savings?.money_saved, savings?.currency_symbol ?? symbol, { compact: true })} saved
            </p>
          </div>
          <div className="w-11 h-11 rounded-2xl bg-white/15 border border-white/25 flex items-center justify-center shrink-0">
            <TrendingUp className="w-5 h-5" />
          </div>
        </div>
      </div>

      {onAnalyzeImpact && (
        <button
          onClick={onAnalyzeImpact}
          className="sm:col-span-2 xl:col-span-4 group flex items-center justify-between bg-slate-900 hover:bg-slate-800 text-white rounded-2xl px-5 py-3.5 transition shadow-xs"
        >
          <span className="text-sm font-bold text-left">
            {hasLoss
              ? `What happens if this ${formatRate(rate)} leak is never repaired?`
              : "Explore the cost of an unrepaired leak"}
          </span>
          <span className="flex items-center space-x-2 text-xs font-bold text-blue-300 shrink-0 ml-4">
            <span>Analyze Impact</span>
            <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
          </span>
        </button>
      )}
    </div>
  );
};
