import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Calculator, Droplets, IndianRupee, ShieldAlert, Sparkles, Users, Container,
  CalendarClock, Info, Zap
} from "lucide-react";
import type { ImpactAnalysis, ImpactConfig } from "../types";
import { formatLitres, formatMoney, formatRate, severityStyle, urgencyStyle } from "../lib/impact";

const DELAY_LABELS: Record<number, string> = {
  1: "1 Day", 7: "1 Week", 30: "30 Days", 90: "90 Days", 365: "1 Year",
};

/**
 * "What if we ignore it?" — the interactive impact simulator.
 *
 * Every number shown comes from POST /api/impact/simulate, i.e. the same
 * backend/impact calculators that score real detections. Nothing is computed
 * in the browser, so the simulator can never quote a figure the detection
 * pipeline wouldn't.
 */
export const ImpactSimulatorView: React.FC = () => {
  const [config, setConfig] = useState<ImpactConfig | null>(null);
  const [leakRate, setLeakRate] = useState(0.62);
  const [delayDays, setDelayDays] = useState(30);
  const [tariff, setTariff] = useState(20);
  const [analysis, setAnalysis] = useState<ImpactAnalysis | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [loadedFromDetector, setLoadedFromDetector] = useState<string | null>(null);

  // Debounce handle — the slider fires continuously, but each change is a
  // round-trip, so only the settled value is sent.
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    fetch("/api/impact/config")
      .then((r) => r.json())
      .then((cfg: ImpactConfig) => {
        setConfig(cfg);
        if (typeof cfg.rate_per_kilolitre === "number") setTariff(cfg.rate_per_kilolitre);
        if (typeof cfg.default_delay_days === "number") setDelayDays(cfg.default_delay_days);
      })
      .catch(() => setConfig(null));
  }, []);

  const simulate = useCallback((rate: number, delay: number, rate_per_kl: number) => {
    setLoading(true);
    fetch("/api/impact/simulate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ leak_rate_lpm: rate, repair_delay_days: delay, tariff_per_kl: rate_per_kl }),
    })
      .then((r) => r.json())
      .then((data) => {
        if (data?.error) {
          setError(data.error);
        } else {
          setAnalysis(data);
          setError(null);
        }
      })
      .catch(() => setError("Impact backend unreachable."))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => simulate(leakRate, delayDays, tariff), 180);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [leakRate, delayDays, tariff, simulate]);

  const loadDetectedLeak = () => {
    fetch("/api/impact/current")
      .then((r) => r.json())
      .then((data) => {
        const rate = data?.analysis?.leak_rate_lpm ?? 0;
        if (data?.leak_detected && rate > 0) {
          setLeakRate(Number(rate.toFixed(2)));
          setLoadedFromDetector(`${data.zone} · ${data.confidence_tier} confidence · ${Number(data.likelihood_score).toFixed(1)}% likelihood`);
        } else {
          setLoadedFromDetector("No leak is currently confirmed by the detector — showing your manual value.");
        }
      })
      .catch(() => setLoadedFromDetector("Could not read the current detector state."));
  };

  const sev = severityStyle(analysis?.severity.label);
  const urg = urgencyStyle(analysis?.recommendation.urgency);
  const symbol = analysis?.cost.currency_symbol ?? config?.currency_symbol ?? "₹";
  const wl = analysis?.water_loss;
  const cost = analysis?.cost;
  const eq = analysis?.progression.at_repair_delay.equivalents;
  const delayOptions = config?.delay_options_days ?? [1, 7, 30, 90, 365];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h2 className="text-xl font-bold text-slate-900 tracking-tight flex items-center space-x-2">
              <Calculator className="w-6 h-6 text-blue-600" />
              <span>Leak Impact Simulator</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1 max-w-2xl">
              What does an unrepaired leak actually cost? Adjust the leak rate, repair delay and water
              tariff to project water loss, financial impact and repair urgency.
            </p>
          </div>
          <button
            onClick={loadDetectedLeak}
            className="px-4 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-bold rounded-xl shadow-2xs flex items-center space-x-2 transition shrink-0"
          >
            <Zap className="w-4 h-4" />
            <span>Load Detected Leak</span>
          </button>
        </div>
        {loadedFromDetector && (
          <p className="mt-3 text-xs text-blue-700 bg-blue-50 border border-blue-100 rounded-xl px-3.5 py-2.5 font-medium">
            {loadedFromDetector}
          </p>
        )}
        {error && (
          <p className="mt-3 text-xs text-rose-700 bg-rose-50 border border-rose-200 rounded-xl px-3.5 py-2.5 font-medium">
            {error}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* Left: controls */}
        <div className="xl:col-span-4 bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs space-y-7 self-start">
          <h3 className="text-sm font-bold text-slate-900">Simulation Inputs</h3>

          {/* Leak rate */}
          <div>
            <div className="flex items-baseline justify-between mb-2">
              <label htmlFor="leak-rate" className="text-xs font-bold text-slate-600 uppercase tracking-wider">Leak Rate</label>
              <span className="text-lg font-extrabold text-blue-600 font-mono">{leakRate.toFixed(2)} <span className="text-xs text-slate-400">L/min</span></span>
            </div>
            <input
              id="leak-rate"
              type="range" min={0.05} max={5} step={0.01}
              value={leakRate}
              onChange={(e) => setLeakRate(Number(e.target.value))}
              className="w-full accent-blue-600 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-semibold mt-1">
              <span>0.05</span><span>2.5</span><span>5.0 L/min</span>
            </div>
            <input
              type="number" min={0} max={100} step={0.01}
              value={leakRate}
              onChange={(e) => {
                const v = Number(e.target.value);
                if (Number.isFinite(v) && v >= 0) setLeakRate(v);
              }}
              className="mt-3 w-full px-3 py-2 border border-slate-200 rounded-xl text-sm font-mono focus:outline-hidden focus:ring-2 focus:ring-blue-500/40"
            />
          </div>

          {/* Repair delay */}
          <div>
            <label className="text-xs font-bold text-slate-600 uppercase tracking-wider block mb-2">Repair Delay</label>
            <div className="grid grid-cols-3 gap-2">
              {delayOptions.map((d) => (
                <button
                  key={d}
                  onClick={() => setDelayDays(d)}
                  className={`px-2 py-2 rounded-xl text-xs font-bold border transition ${
                    delayDays === d
                      ? "bg-blue-600 text-white border-blue-600 shadow-2xs"
                      : "bg-white text-slate-600 border-slate-200 hover:border-blue-300 hover:text-blue-600"
                  }`}
                >
                  {DELAY_LABELS[d] ?? `${d} Days`}
                </button>
              ))}
            </div>
          </div>

          {/* Tariff */}
          <div>
            <div className="flex items-baseline justify-between mb-2">
              <label htmlFor="tariff" className="text-xs font-bold text-slate-600 uppercase tracking-wider">Water Tariff</label>
              <span className="text-xs text-slate-400 font-semibold">per 1000 L</span>
            </div>
            <div className="flex items-center space-x-2">
              <span className="text-lg font-extrabold text-slate-500">{symbol}</span>
              <input
                id="tariff"
                type="number" min={0.01} step={0.5}
                value={tariff}
                onChange={(e) => {
                  const v = Number(e.target.value);
                  if (Number.isFinite(v) && v > 0) setTariff(v);
                }}
                className="flex-1 px-3 py-2 border border-slate-200 rounded-xl text-sm font-mono focus:outline-hidden focus:ring-2 focus:ring-blue-500/40"
              />
            </div>
          </div>

          {/* Severity bands reference */}
          {config?.severity_bands && (
            <div className="pt-1">
              <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-2">Severity Bands</p>
              <div className="space-y-1.5">
                {config.severity_bands.map((b) => {
                  const s = severityStyle(b.label);
                  const active = analysis?.severity.label === b.label;
                  return (
                    <div
                      key={b.label}
                      className={`flex items-center justify-between text-[11px] px-2.5 py-1.5 rounded-lg border ${
                        active ? s.badge : "bg-slate-50 text-slate-500 border-slate-200/70"
                      }`}
                    >
                      <span className="font-bold">{s.emoji} {b.label}</span>
                      <span className="font-mono">
                        {b.min_lpm.toFixed(1)}{b.max_lpm === null ? "+" : `–${b.max_lpm.toFixed(1)}`} L/min
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </div>

        {/* Center: impact cards */}
        <div className="xl:col-span-5 space-y-5">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
            <ImpactCard
              icon={<Droplets className="w-5 h-5" />} tone="blue"
              label="Water Lost / Day" value={formatLitres(wl?.litres_per_day, { compact: true })}
              sub={`${formatLitres(wl?.litres_per_hour)} per hour`} loading={loading && !analysis}
            />
            <ImpactCard
              icon={<IndianRupee className="w-5 h-5" />} tone="rose"
              label="Cost / Month" value={formatMoney(cost?.cost_per_month, symbol, { compact: true })}
              sub={`${formatMoney(cost?.cost_per_day, symbol)} per day`} loading={loading && !analysis}
            />
            <ImpactCard
              icon={<Droplets className="w-5 h-5" />} tone="indigo"
              label="Annual Water Loss" value={formatLitres(wl?.litres_per_year, { compact: true })}
              sub={`${formatLitres(wl?.litres_per_month, { compact: true })} per month`} loading={loading && !analysis}
            />
            <ImpactCard
              icon={<IndianRupee className="w-5 h-5" />} tone="amber"
              label="Annual Cost" value={formatMoney(cost?.cost_per_year, symbol, { compact: true })}
              sub={`at ${symbol}${tariff}/1000 L`} loading={loading && !analysis}
            />
          </div>

          {/* Severity + recommendation */}
          <div className={`bg-white rounded-2xl border p-6 shadow-xs ${sev.ring}`}>
            <div className="flex items-start justify-between gap-4">
              <div className="min-w-0">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">Severity Classification</h3>
                <div className="flex items-center space-x-2.5 mt-2">
                  <span className="text-2xl leading-none">{sev.emoji}</span>
                  <span className={`px-3 py-1.5 rounded-xl text-lg font-extrabold border ${sev.badge}`}>
                    {analysis?.severity.label ?? "—"}
                  </span>
                </div>
              </div>
              <div className={`w-12 h-12 rounded-2xl border flex items-center justify-center shrink-0 ${sev.badge}`}>
                <ShieldAlert className="w-6 h-6" />
              </div>
            </div>

            <div className="mt-5 pt-5 border-t border-slate-100">
              <div className="flex items-center space-x-2 mb-2">
                <span className={`px-2.5 py-1 rounded-lg text-[10px] font-extrabold border ${urg.badge}`}>
                  {analysis?.recommendation.urgency ?? "—"}
                </span>
                <h4 className="text-sm font-bold text-slate-800">{analysis?.recommendation.headline ?? "—"}</h4>
              </div>
              <p className="text-xs text-slate-500 leading-relaxed">{analysis?.recommendation.action ?? ""}</p>
            </div>
          </div>

          {/* Relatable equivalents */}
          <div className="bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs">
            <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
              <Sparkles className="w-4 h-4 text-amber-500" />
              <span>What {formatLitres(analysis?.progression.at_repair_delay.litres, { compact: true })} actually means</span>
            </h3>
            <p className="text-[11px] text-slate-400 mt-0.5 mb-4">
              Water lost over a {analysis?.progression.repair_delay_days ?? delayDays}-day repair delay
            </p>
            <div className="grid grid-cols-2 gap-4">
              <EquivalentTile
                icon={<Container className="w-5 h-5" />}
                value={eq ? eq.water_tanks.toLocaleString(undefined, { maximumFractionDigits: 1 }) : "—"}
                label={`Household tanks (${eq?.tank_size_litres ?? 200} L each)`}
              />
              <EquivalentTile
                icon={<Users className="w-5 h-5" />}
                value={eq ? eq.people_daily_supply.toLocaleString(undefined, { maximumFractionDigits: 1 }) : "—"}
                label={`People's daily supply (${eq?.person_daily_litres ?? 135} L/person)`}
              />
            </div>
          </div>
        </div>

        {/* Right: progression visual */}
        <div className="xl:col-span-3 bg-white rounded-2xl border border-slate-200/80 p-6 shadow-xs self-start">
          <h3 className="text-sm font-bold text-slate-900 flex items-center space-x-2">
            <CalendarClock className="w-4 h-4 text-blue-600" />
            <span>If Nobody Fixes It</span>
          </h3>
          <p className="text-[11px] text-slate-400 mt-0.5 mb-5">Cumulative loss at {formatRate(leakRate)}</p>

          <div className="space-y-4">
            {(analysis?.progression.timeline ?? []).map((point) => (
              <div key={point.label}>
                <div className="flex items-baseline justify-between mb-1.5">
                  <span className="text-xs font-bold text-slate-700">{point.label}</span>
                  <span className="text-xs font-extrabold text-slate-900 font-mono">
                    {formatLitres(point.litres, { compact: true })}
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-slate-100 overflow-hidden">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ease-out ${sev.bar}`}
                    style={{ width: `${Math.max(2, point.fill_ratio * 100)}%` }}
                  />
                </div>
                <p className="text-[11px] text-slate-400 font-semibold mt-1">
                  {formatMoney(point.cost, symbol, { compact: true })}
                </p>
              </div>
            ))}
          </div>

          <div className="mt-6 pt-5 border-t border-slate-100">
            <p className="text-[11px] font-bold text-slate-500 uppercase tracking-wider mb-1.5">
              At your {analysis?.progression.repair_delay_days ?? delayDays}-day delay
            </p>
            <p className="text-2xl font-extrabold text-slate-900 tracking-tight">
              {formatLitres(analysis?.progression.at_repair_delay.litres, { compact: true })}
            </p>
            <p className="text-sm font-bold text-rose-600 mt-0.5">
              {formatMoney(analysis?.progression.at_repair_delay.cost, symbol, { compact: true })} lost
            </p>
          </div>

          <p className="mt-5 text-[11px] text-slate-400 leading-relaxed flex items-start space-x-1.5">
            <Info className="w-3.5 h-3.5 shrink-0 mt-0.5" />
            <span>{analysis?.progression.assumptions ?? ""}</span>
          </p>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="bg-amber-50 border border-amber-200 rounded-2xl px-5 py-4">
        <p className="text-xs text-amber-800 font-medium leading-relaxed">
          <strong>Indicative only.</strong> {analysis?.disclaimer ?? "Impact figures are projections derived from the estimated leak rate and the configured water tariff. Field verification is required before any repair action."}
        </p>
      </div>
    </div>
  );
};

const TONE_CLASSES: Record<string, string> = {
  blue: "bg-blue-50 border-blue-100 text-blue-600",
  rose: "bg-rose-50 border-rose-100 text-rose-600",
  indigo: "bg-indigo-50 border-indigo-100 text-indigo-600",
  amber: "bg-amber-50 border-amber-100 text-amber-600",
};

const ImpactCard: React.FC<{
  icon: React.ReactNode; tone: string; label: string; value: string; sub: string; loading?: boolean;
}> = ({ icon, tone, label, value, sub, loading }) => (
  <div className="bg-white rounded-2xl p-5 border border-slate-200/80 shadow-xs">
    <div className="flex items-start justify-between">
      <div className="min-w-0">
        <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">{label}</h3>
        <p className={`text-2xl font-extrabold text-slate-900 mt-1.5 tracking-tight transition-opacity ${loading ? "opacity-40" : "opacity-100"}`}>
          {value}
        </p>
        <p className="text-xs text-slate-400 font-medium mt-1">{sub}</p>
      </div>
      <div className={`w-11 h-11 rounded-2xl border flex items-center justify-center shrink-0 ${TONE_CLASSES[tone]}`}>
        {icon}
      </div>
    </div>
  </div>
);

const EquivalentTile: React.FC<{ icon: React.ReactNode; value: string; label: string }> = ({ icon, value, label }) => (
  <div className="bg-slate-50 border border-slate-200/70 rounded-2xl p-4">
    <div className="w-9 h-9 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-slate-600 mb-2.5">
      {icon}
    </div>
    <p className="text-xl font-extrabold text-slate-900 tracking-tight">{value}</p>
    <p className="text-[11px] text-slate-500 font-medium leading-snug mt-0.5">{label}</p>
  </div>
);
