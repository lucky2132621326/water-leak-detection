import React, { useEffect, useMemo, useRef, useState } from "react";
import { ShieldAlert, Zap, Moon, Activity, Cpu, Scale, Gauge, ChevronDown, ChevronRight } from "lucide-react";
import { DeltaRow, Sparkline, deltaState, pushSample } from "./DetectionDeltas";
import { CHANNEL_EXPLANATIONS, CHANNEL_LABELS } from "./detectionExplanations";

interface DetectionEngineViewProps {
  evaluation: any;
}

// Colour per channel. NOT a list of which channels exist — that comes from the
// config the engine actually published, so the panel shows 6 weights in live and
// 7 in mock without either count being written down here. The previous hardcoded
// five-row list silently omitted acoustic_ml and pressure_drop, so the published
// formula did not describe the running engine.
const WEIGHT_TONES: Record<string, string> = {
  mass_balance: "text-blue-600 dark:text-blue-400",
  current_signature: "text-purple-600 dark:text-purple-400",
  cusum: "text-emerald-600 dark:text-emerald-400",
  mnf: "text-amber-600 dark:text-amber-400",
  acoustic: "text-rose-600 dark:text-rose-400",
  acoustic_ml: "text-amber-600 dark:text-amber-400",
  pressure_drop: "text-violet-600 dark:text-violet-400",
};

const THRESHOLD_LABELS: Record<string, string> = {
  mass_balance_sigma: "Mass balance sigma",
  mass_balance_persistence_samples: "Persistence (samples)",
  current_drop_ma: "Current drop (mA)",
  cusum_k: "CUSUM slack k",
  cusum_h: "CUSUM decision h",
  mnf_window: "MNF night window",
};

interface PlausibilityGuardConfig {
  enabled: boolean;
  current_ma_per_leak_lpm: number;
  acoustic_min_residual_lpm: number;
  margin: number;
  min_residual_lpm: number;
  rule: string;
}

interface DetectorConfig {
  mode?: string;
  channels?: string[];
  channel_count?: number;
  /** Startup state of the ML channel, independent of telemetry — so the reason
   *  it is withheld is knowable before any sample has arrived. */
  acoustic_ml?: {
    enabled: boolean;
    available: boolean;
    unavailable_reason: string | null;
    awaiting_physical_training: boolean;
    bundle_note: string | null;
  };
  weights: Record<string, number>;
  formula: string;
  thresholds: Record<string, string | number>;
  plausibility_guard?: PlausibilityGuardConfig;
}

export const DetectionEngineView: React.FC<DetectionEngineViewProps> = ({ evaluation }) => {
  const [config, setConfig] = useState<DetectorConfig | null>(null);

  // Weights, channel set and ML availability are per-MODE config, not telemetry.
  // Re-fetched when the mode changes so a live/mock switch does not leave the
  // panel describing the previous mode's engine.
  const activeMode = evaluation?.mode;
  useEffect(() => {
    fetch("/api/detectors/config")
      .then((r) => r.json())
      .then(setConfig)
      .catch(() => setConfig(null));
  }, [activeMode]);

  const detectors = evaluation?.detectors;
  const fusion = evaluation?.fusion;
  const sensorFault = evaluation?.sensor_fault;

  const massBalance = detectors?.mass_balance;
  const currentSig = detectors?.current_signature;
  const mnf = detectors?.mnf;
  const cusum = detectors?.cusum;
  const acoustic = detectors?.acoustic;
  const acousticMl = detectors?.acoustic_ml;
  const pressure = detectors?.pressure_drop;
  // Provenance travels with the numbers so a confidence cannot be rendered
  // without the caveat that qualifies it.
  const modelProvenance = evaluation?.model_provenance;
  const simulatedPressure = evaluation?.simulated_channels?.pressure_drop;
  const crossedAt = evaluation?.channel_crossed_at ?? {};

  // Live mode refuses a synthetic bundle by design, which is a DIFFERENT state
  // from a missing model file or a broken sensor. It deserves its own wording:
  // the channel is built and wired, it is simply waiting for a model trained on
  // real rig data. Showing a bare "UNAVAILABLE" would read as a fault.
  // Config first, telemetry second. In live mode with no rig attached there is
  // no detector result to inspect, but the channel is still refused and the UI
  // must be able to say so — that is precisely the state a rig sits in before
  // the ESP32 first reports.
  const mlAwaitingTraining =
    config?.acoustic_ml?.awaiting_physical_training === true ||
    (acousticMl != null && !acousticMl.active &&
     typeof acousticMl.reason === "string" &&
     acousticMl.reason.includes("refused in live mode"));

  // No telemetry at all — live mode before any hardware has reported. The cards
  // below would otherwise render 0.0% confidence everywhere, which reads as a
  // working system reporting zeros rather than an absence of data.
  const hasTelemetry = evaluation?.ts != null;

  const [showExplanations, setShowExplanations] = useState(false);

  // Rolling 60s history per channel, kept client-side. The backend already
  // publishes one sample per second and the page polls at that rate, so a ring
  // buffer here avoids a new history endpoint just to draw a sparkline.
  // Keyed on `ts` so a paused or repeated poll does not double-count a sample.
  const [series, setSeries] = useState<Record<string, number[]>>({});
  const lastTs = useRef<number | null>(null);

  useEffect(() => {
    const ts = evaluation?.ts;
    if (ts == null || ts === lastTs.current) return;
    lastTs.current = ts;
    setSeries((prev) => ({
      mass_balance: pushSample(prev.mass_balance ?? [], massBalance?.residual),
      current_signature: pushSample(prev.current_signature ?? [], currentSig?.current_ma),
      acoustic: pushSample(prev.acoustic ?? [], acoustic?.ratio),
      acoustic_ml: pushSample(prev.acoustic_ml ?? [], acousticMl?.probability),
      cusum: pushSample(prev.cusum ?? [], cusum?.cusum_score),
      mnf: pushSample(prev.mnf ?? [], mnf?.residual),
      pressure_drop: pushSample(prev.pressure_drop ?? [], pressure?.pressure_bar),
    }));
  }, [evaluation?.ts]);

  // Each channel expresses "how far from normal" in its own natural units, so
  // the delta strings are built per channel rather than from one formula.
  const deltas = useMemo(() => {
    const sigmaMult = massBalance?.sigma_multiple;
    const mbProgress = massBalance?.threshold
      ? Math.abs(massBalance.residual ?? 0) / massBalance.threshold : null;

    const expected = currentSig?.expected_current_ma;
    const actual = currentSig?.current_ma;
    const currentPct = expected ? ((actual - expected) / expected) * 100 : null;
    const currentDrop = currentSig?.residual_ma;
    const currentThresh = config?.thresholds?.current_drop_ma as number | undefined;

    const ratio = acoustic?.ratio;
    const ratioThresh = acoustic?.ratio_threshold;

    const prob = acousticMl?.probability;
    const probBase = acousticMl?.baseline_probability;
    const probThresh = acousticMl?.threshold;

    return {
      massBalance: {
        delta: sigmaMult == null ? null : `${sigmaMult >= 0 ? "+" : ""}${sigmaMult.toFixed(1)}σ`,
        state: deltaState(mbProgress),
        progress: mbProgress,
      },
      current: {
        delta: currentDrop == null ? null
          : `${currentDrop >= 0 ? "−" : "+"}${Math.abs(currentDrop).toFixed(1)} mA` +
            (currentPct == null ? "" : ` (${currentPct >= 0 ? "+" : ""}${currentPct.toFixed(1)}%)`),
        state: deltaState(currentDrop != null && currentThresh ? currentDrop / currentThresh : null),
      },
      acoustic: {
        delta: ratio == null ? null : `ratio ${ratio.toFixed(2)} / ${Number(ratioThresh ?? 0).toFixed(2)}`,
        state: deltaState(ratio != null && ratioThresh ? ratio / ratioThresh : null),
      },
      ml: {
        delta: prob == null ? null
          : `${probBase == null ? "" : `${probBase.toFixed(2)} → `}${prob.toFixed(3)}`,
        state: deltaState(prob != null && probThresh ? prob / probThresh : null),
      },
    };
  }, [evaluation?.ts, config]);

  // Ignition order — computed from server timestamps so a dashboard opened
  // mid-leak still shows the real sequence rather than starting its own clock.
  const ignition = useMemo(() => {
    const entries = Object.entries(crossedAt) as [string, number][];
    if (!entries.length) return [];
    const first = Math.min(...entries.map(([, v]) => v));
    return entries
      .sort((a, b) => a[1] - b[1])
      .map(([method, ts]) => ({ method, offset: ts - first }));
  }, [evaluation?.ts]);

  return (
    <div className="space-y-6">
      {/* A withheld alarm must never look like an all-clear. The flow meters are
          claiming a leak the pump current and pipe acoustics say is impossible, which
          means an instrument has almost certainly failed — the operator needs
          that, not silence. */}
      {sensorFault?.is_fault && (
        <div className="bg-amber-50 border border-amber-300 rounded-2xl p-5">
          <h3 className="text-sm font-bold text-amber-900 flex items-center space-x-2">
            <Gauge className="w-4 h-4" />
            <span>Instrument Fault — leak alarm withheld</span>
          </h3>
          <p className="text-xs text-amber-800 mt-2 leading-relaxed">
            {sensorFault.hypothesis}
          </p>
          <p className="text-[11px] text-amber-700/90 mt-2 font-mono leading-relaxed">
            {sensorFault.detail}
          </p>
          {sensorFault.contradicting_channels?.length > 0 && (
            <p className="text-[11px] text-amber-700/80 mt-2">
              Contradicted by: {sensorFault.contradicting_channels.join(", ")}
            </p>
          )}
        </div>
      )}

      {/* No telemetry yet. Live mode before any hardware has reported is
          LEGITIMATELY empty, and that is worth stating plainly — the detector
          cards below would otherwise show 0.0% confidence and "—" everywhere,
          which reads as a working system reporting all-clear rather than a
          system that has not heard from anything. Never backfilled with mock
          values: an empty live rig has no readings to show. */}
      {!hasTelemetry && (
        <div className="bg-white dark:bg-slate-900 border border-dashed border-slate-300 dark:border-slate-700 rounded-2xl p-8 text-center">
          <Activity className="w-6 h-6 text-slate-300 dark:text-slate-600 mx-auto" />
          <h3 className="text-sm font-bold text-slate-700 dark:text-slate-300 mt-3">
            No telemetry yet
          </h3>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1.5 max-w-md mx-auto leading-relaxed">
            No samples have reached the detection pipeline. In Live Sensor mode this is the
            correct state until the ESP32 publishes to the broker — run an experiment to
            begin. The channels below stay listed so you can see what will be evaluated,
            but they hold no readings.
          </p>
        </div>
      )}

      {/* MOMENT OF DETECTION — the core story: separate sensors, separate
          physics, same conclusion, different speeds. Offsets come from server
          timestamps, so opening the dashboard mid-leak still shows the real
          sequence instead of restarting the clock. Renders only during an
          episode; there is nothing honest to show when nothing has fired. */}
      {ignition.length > 0 && (
        <div className="bg-white dark:bg-slate-900 border border-rose-200 dark:border-rose-900/60 rounded-2xl p-5 shadow-xs">
          <div className="flex items-center justify-between mb-3.5">
            <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
              <ShieldAlert className="w-4 h-4 text-rose-600" />
              <span>Moment of Detection</span>
            </h3>
            <span className="text-[11px] text-slate-400">
              {ignition.length} channel{ignition.length === 1 ? "" : "s"} crossed threshold
              {" · "}
              {new Set(ignition.map((i) => (
                i.method === "current_signature" ? "current"
                : i.method.startsWith("acoustic") ? "vibration"
                : i.method === "pressure_drop" ? "pressure" : "flow"))).size} independent sensor group(s)
            </span>
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            {ignition.map(({ method, offset }) => {
              const d =
                method === "mass_balance" || method === "Mass_Balance" ? deltas.massBalance
                : method === "current_signature" ? deltas.current
                : method === "acoustic" ? deltas.acoustic
                : method === "acoustic_ml" ? deltas.ml
                : null;
              return (
                <div key={method} className="bg-rose-50/60 dark:bg-rose-950/30 border border-rose-200/70 dark:border-rose-900/50 rounded-xl px-3 py-2.5">
                  <div className="text-[10px] uppercase tracking-wide text-slate-500 dark:text-slate-400 font-semibold truncate">
                    {CHANNEL_LABELS[method] ?? method}
                  </div>
                  <div className="font-mono text-sm font-extrabold text-rose-600 dark:text-rose-400 mt-0.5">
                    {d?.delta ?? "fired"}
                  </div>
                  {/* Time relative to the FIRST channel to fire, not wall clock —
                      the gap between channels is the interesting quantity. */}
                  <div className="text-[10px] text-slate-400 font-mono mt-0.5">
                    {offset === 0 ? "first" : `+${offset.toFixed(0)}s`}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Banner */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold text-slate-900 flex items-center space-x-2 tracking-tight">
              <ShieldAlert className="w-6 h-6 text-rose-600" />
              <span>Phase 2 & 3: Multi-Algorithm Detection & Sensor Fusion Engine</span>
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              Parallel evaluation of Mass Balance (3-Sigma), Motor Current Signature, Minimum Night Flow, CUSUM residual drift, Acoustic band energy and the Acoustic ML classifier — fused across independent sensor groups.
            </p>
          </div>

          <div className="flex items-center space-x-4">
            <div className="text-right">
              <div className="text-xs text-slate-400 font-medium">Fused Confidence Index</div>
              <div className="text-2xl font-black text-slate-900">
                {fusion?.fused_confidence == null ? "—" : `${(fusion.fused_confidence * 100).toFixed(1)}%`}
              </div>
            </div>
            <div className={`px-3.5 py-1.5 rounded-full text-xs font-bold border ${
              Boolean(fusion?.is_alarm)
                ? "bg-rose-100 text-rose-700 border-rose-200 animate-pulse"
                : "bg-emerald-100 text-emerald-700 border-emerald-200"
            }`}>
              {fusion?.severity || "NONE"}
            </div>
          </div>
        </div>
      </div>

      {/* 4 Detectors Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5">
        {/* 1. Mass Balance */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(massBalance?.is_alarm) ? "border-rose-300 bg-rose-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Scale className="w-4 h-4 text-blue-600" />
              <h3 className="text-sm font-bold text-slate-900">Mass Balance (3-Sigma)</h3>
            </div>
            {(Boolean(massBalance?.is_alarm)) ? (
              <span className="text-[10px] bg-rose-600 text-white px-2 py-0.5 rounded-full font-bold">ALARM</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <DeltaRow
              label="Residual vs baseline"
              baseline={massBalance?.baseline}
              current={massBalance?.residual}
              unit="L/min"
              digits={3}
              delta={deltas.massBalance.delta}
              state={deltas.massBalance.state}
            />
            <Sparkline points={series.mass_balance ?? []} state={deltas.massBalance.state}
                       threshold={massBalance?.threshold} />
            <div className="flex justify-between text-slate-500">
              <span>Threshold (3σ):</span>
              <span className="font-mono text-slate-700 font-semibold">{massBalance?.threshold == null ? "—" : `${massBalance.threshold} L/min`}</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-blue-600">{massBalance?.confidence == null ? "—" : `${(massBalance.confidence * 100).toFixed(1)}%`}</span>
            </div>
          </div>
        </div>

        {/* 2. Current Signature */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(currentSig?.is_alarm) ? "border-purple-300 bg-purple-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Zap className="w-4 h-4 text-purple-600" />
              <h3 className="text-sm font-bold text-slate-900">Current Signature</h3>
            </div>
            {(Boolean(currentSig?.is_alarm)) ? (
              <span className="text-[10px] bg-purple-600 text-white px-2 py-0.5 rounded-full font-bold">ALARM</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <DeltaRow
              label="Expected vs measured"
              baseline={currentSig?.expected_current_ma}
              current={currentSig?.current_ma}
              unit="mA"
              digits={1}
              delta={deltas.current.delta}
              state={deltas.current.state}
            />
            <Sparkline points={series.current_signature ?? []} state={deltas.current.state}
                       threshold={currentSig?.expected_current_ma} />
            <div className="flex justify-between text-slate-500">
              <span>Transient ΔI:</span>
              <span className="font-mono text-slate-700 font-semibold">{currentSig?.current_delta_ma == null ? "—" : `${currentSig.current_delta_ma} mA`}</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-purple-600">{currentSig?.confidence == null ? "—" : `${(currentSig.confidence * 100).toFixed(1)}%`}</span>
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
              <span className="font-mono text-slate-900 font-bold">{mnf?.baseline_lpm == null ? "—" : `${Number(mnf.baseline_lpm).toFixed(2)} L/min`}</span>
            </div>
            <div className="flex justify-between text-slate-500">
              <span>Night Residual:</span>
              <span className="font-mono text-slate-700 font-semibold">{mnf?.residual == null ? "—" : `${Number(mnf.residual).toFixed(3)} L/min`}</span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-amber-600">{mnf?.confidence == null ? "—" : `${(mnf.confidence * 100).toFixed(1)}%`}</span>
            </div>
          </div>
        </div>

        {/* 4. CUSUM */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(cusum?.is_alarm) ? "border-emerald-300 bg-emerald-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Activity className="w-4 h-4 text-emerald-600" />
              <h3 className="text-sm font-bold text-slate-900">CUSUM Micro-Leak</h3>
            </div>
            {Boolean(cusum?.is_alarm) ? (
              <span className="text-[10px] bg-amber-500 text-white px-2 py-0.5 rounded-full font-bold">SUSPECT</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            {/* `cusum_score`, not `score`. The old name never existed on the
                response, so `?? 0` silently rendered a constant zero next to a
                100% confidence — the same fallback-masks-a-typo failure as the
                MNF card's `?? 0.700`. */}
            <DeltaRow
              label="Accumulated drift vs decision h"
              baseline={0}
              current={cusum?.cusum_score}
              digits={2}
              delta={cusum?.cusum_score == null ? null
                : `${cusum.cusum_score.toFixed(2)} / ${Number(cusum.threshold_h ?? 0).toFixed(2)}`}
              state={deltaState(
                cusum?.cusum_score != null && cusum?.threshold_h
                  ? cusum.cusum_score / cusum.threshold_h : null)}
            />
            <Sparkline points={series.cusum ?? []}
                       state={deltaState(
                         cusum?.cusum_score != null && cusum?.threshold_h
                           ? cusum.cusum_score / cusum.threshold_h : null)}
                       threshold={cusum?.threshold_h} />
            <div className="flex justify-between text-slate-500">
              <span>Decision Threshold h:</span>
              {/* Was hardcoded "3.00" while thresholds.yaml sets 5.0 — the
                  published figure did not describe the running engine. */}
              <span className="font-mono text-slate-700 font-semibold">
                {cusum?.threshold_h != null ? Number(cusum.threshold_h).toFixed(2) : "—"}
              </span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-emerald-600">{cusum?.confidence == null ? "—" : `${(cusum.confidence * 100).toFixed(1)}%`}</span>
            </div>
          </div>
        </div>

        {/* 5. Acoustic signature — optional when no vibration sensor is fitted */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(acoustic?.is_alarm) ? "border-rose-300 bg-rose-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Gauge className="w-4 h-4 text-rose-600" />
              <h3 className="text-sm font-bold text-slate-900">Acoustic Signature</h3>
            </div>
            {!acoustic?.active ? (
              <span className="text-[10px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full font-bold">INACTIVE</span>
            ) : Boolean(acoustic?.is_alarm) ? (
              <span className="text-[10px] bg-rose-600 text-white px-2 py-0.5 rounded-full font-bold">ALARM</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            <DeltaRow
              label="Band-mid vs clean baseline"
              baseline={acoustic?.baseline_band_mid}
              current={acoustic?.band_mid}
              digits={3}
              delta={deltas.acoustic.delta}
              state={deltas.acoustic.state}
            />
            <Sparkline points={series.acoustic ?? []} state={deltas.acoustic.state}
                       threshold={acoustic?.ratio_threshold} />
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-rose-600">
                {acoustic?.confidence == null ? "—" : `${(acoustic.confidence * 100).toFixed(1)}%`}
              </span>
            </div>
            {!acoustic?.active && (
              <p className="text-[10px] text-slate-400 leading-snug pt-1">
                No vibration sample — the fusion engine redistributes this channel's weight.
              </p>
            )}
          </div>
        </div>

        {/* 6. Acoustic ML — the classifier. Its provenance note is rendered in
            the banner above, so a confidence here is never seen without it. */}
        <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
          Boolean(acousticMl?.is_alarm) ? "border-amber-300 bg-amber-50/30" : "border-slate-200/80"
        }`}>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center space-x-2">
              <Cpu className="w-4 h-4 text-amber-600" />
              <h3 className="text-sm font-bold text-slate-900">Acoustic ML</h3>
            </div>
            {mlAwaitingTraining ? (
              <span className="text-[10px] bg-sky-100 text-sky-700 dark:bg-sky-900/50 dark:text-sky-300 px-2 py-0.5 rounded-full font-bold">
                AWAITING TRAINING
              </span>
            ) : !acousticMl?.active ? (
              <span className="text-[10px] bg-slate-100 text-slate-500 px-2 py-0.5 rounded-full font-bold">UNAVAILABLE</span>
            ) : Boolean(acousticMl?.is_alarm) ? (
              <span className="text-[10px] bg-amber-600 text-white px-2 py-0.5 rounded-full font-bold">ALARM</span>
            ) : (
              <span className="text-[10px] bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full font-bold">OK</span>
            )}
          </div>
          <div className="space-y-2 text-xs">
            {!mlAwaitingTraining && (
              <>
                <DeltaRow
                  label="Probability vs quiet baseline"
                  baseline={acousticMl?.baseline_probability}
                  current={acousticMl?.probability}
                  digits={3}
                  delta={deltas.ml.delta}
                  state={deltas.ml.state}
                />
                <Sparkline points={series.acoustic_ml ?? []} state={deltas.ml.state}
                           threshold={acousticMl?.threshold} />
              </>
            )}
            <div className="flex justify-between text-slate-500">
              <span>Pump Duty:</span>
              <span className="font-mono text-slate-700 font-semibold">
                {acousticMl?.pump_duty != null ? Number(acousticMl.pump_duty).toFixed(1) : "—"}
              </span>
            </div>
            <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
              <span className="text-slate-500 font-medium">Channel Confidence:</span>
              <span className="font-extrabold text-amber-600">
                {acousticMl?.confidence == null ? "—" : `${(acousticMl.confidence * 100).toFixed(1)}%`}
              </span>
            </div>
            {/* The only remaining synthetic marker. Low emphasis by design, but
                never removable: a judge reading the screen unaided must not take
                a synthetic model's score for a measurement. */}
            {acousticMl?.is_synthetic_model && (
              <p className="text-[10px] text-amber-600 dark:text-amber-500 leading-snug pt-1 border-t border-slate-100 dark:border-slate-800 mt-2">
                Model: {modelProvenance?.note ?? "SYNTHETIC"} — demonstration, not a measurement of this rig.
              </p>
            )}
            {mlAwaitingTraining ? (
              // The card stays VISIBLE in live mode — hiding it would erase the
              // fact that this channel exists and is deliberately withheld.
              <div className="text-[10px] text-sky-700 dark:text-sky-300 leading-snug pt-1 border-t border-slate-100 dark:border-slate-800 mt-2 space-y-1">
                <p className="font-bold">Awaiting physical training data.</p>
                <p className="text-slate-500 dark:text-slate-400">
                  The loaded model was trained on generated data, so it describes the
                  generator rather than this pipe. It is refused in live mode until a
                  bundle trained on operator-logged leak events is loaded. No score is
                  shown because none would be meaningful.
                </p>
              </div>
            ) : !acousticMl?.active && acousticMl?.reason ? (
              <p className="text-[10px] text-slate-400 leading-snug pt-1">{acousticMl.reason}</p>
            ) : null}
          </div>
        </div>

        {/* 7. SIMULATED pressure — MOCK ONLY. Renders only when the channel
            exists at all, which it never does in live mode. */}
        {pressure && (
          <div className={`bg-white border rounded-2xl p-5 shadow-xs transition ${
            Boolean(pressure?.is_alarm) ? "border-violet-300 bg-violet-50/30" : "border-violet-200/80"
          }`}>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2">
                <Gauge className="w-4 h-4 text-violet-600" />
                <h3 className="text-sm font-bold text-slate-900">Pressure Drop</h3>
              </div>
              <span className="text-[10px] bg-violet-600 text-white px-2 py-0.5 rounded-full font-bold">SIMULATED</span>
            </div>
            <div className="space-y-2 text-xs">
              <div className="flex justify-between text-slate-500">
                <span>Line Pressure:</span>
                <span className="font-mono text-slate-900 font-bold">
                  {pressure?.pressure_bar != null ? `${Number(pressure.pressure_bar).toFixed(3)} bar` : "—"}
                </span>
              </div>
              <div className="flex justify-between text-slate-500">
                <span>Drop / Threshold:</span>
                <span className="font-mono text-slate-700 font-semibold">
                  {pressure?.threshold_bar != null
                    ? `${Number(pressure.drop_bar).toFixed(3)} / ${Number(pressure.threshold_bar).toFixed(3)}`
                    : "—"}
                </span>
              </div>
              <div className="mt-3 pt-2.5 border-t border-slate-100 flex justify-between items-center">
                <span className="text-slate-500 font-medium">Channel Confidence:</span>
                <span className="font-extrabold text-violet-600">
                  {pressure?.confidence == null ? "—" : `${(pressure.confidence * 100).toFixed(1)}%`}
                </span>
              </div>
              {/* Same rule as the ML marker: quiet, but always present. */}
              <p className="text-[10px] text-violet-600 dark:text-violet-400 leading-snug pt-1 border-t border-slate-100 dark:border-slate-800 mt-2">
                Simulated channel — the physical rig has no pressure sensor.
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Fusion weights — fetched from /api/detectors/config so the formula
          shown is the one the engine is actually running. It previously
          hardcoded 0.20 for Current and MNF, which did not match the code. */}
      <div className="bg-white border border-slate-200/80 rounded-2xl p-6 shadow-xs">
        <h3 className="text-sm font-bold text-slate-900 mb-2 flex items-center space-x-2">
          <Cpu className="w-4 h-4 text-blue-600" />
          <span>Multi-Sensor Confidence Fusion Algorithm Weights</span>
        </h3>
        <p className="text-xs text-slate-500 mb-5 font-mono">
          {config
            ? `Confidence = ${config.formula}`
            : "Loading fusion configuration…"}
        </p>

        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-4 text-xs">
          {(Object.entries(config?.weights ?? {}) as [string, number][])
            .sort((a, b) => b[1] - a[1])
            .map(([key, weight]) => (
              <div key={key} className="bg-slate-50 dark:bg-slate-800/60 p-4 rounded-xl border border-slate-200/70 dark:border-slate-700">
                <div className="text-slate-500 dark:text-slate-400 font-medium">
                  {CHANNEL_LABELS[key] ?? key}
                  {key === "pressure_drop" && (
                    <span className="ml-1 text-[9px] text-violet-500">SIM</span>
                  )}
                </div>
                <div className={`text-xl font-extrabold mt-1 ${WEIGHT_TONES[key] ?? "text-slate-600"}`}>
                  {(weight * 100).toFixed(0)}%
                </div>
              </div>
            ))}
          {!config?.weights && (
            <div className="col-span-full text-slate-400">Loading fusion configuration…</div>
          )}
        </div>

        {config?.thresholds && (
          <div className="mt-5 pt-5 border-t border-slate-100 grid grid-cols-2 md:grid-cols-3 gap-3 text-[11px]">
            {Object.entries(config.thresholds).map(([k, v]) => (
              <div key={k} className="flex justify-between">
                <span className="text-slate-400 font-medium">{THRESHOLD_LABELS[k] ?? k}</span>
                <span className="font-mono font-bold text-slate-700">{String(v)}</span>
              </div>
            ))}
          </div>
        )}

        {/* The guard can veto a fused alarm, so publishing the weights alone
            would overstate what decides an alarm. */}
        {config?.plausibility_guard && (
          <div className="mt-5 pt-5 border-t border-slate-100">
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs font-bold text-slate-900 flex items-center space-x-2">
                <Scale className="w-4 h-4 text-indigo-600" />
                <span>Physical Plausibility Guard</span>
              </span>
              <span
                className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                  config.plausibility_guard.enabled
                    ? "bg-indigo-50 text-indigo-700"
                    : "bg-slate-100 text-slate-500"
                }`}
              >
                {config.plausibility_guard.enabled ? "ACTIVE" : "DISABLED"}
              </span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              {config.plausibility_guard.rule}
            </p>
            <div className="mt-3 grid grid-cols-2 md:grid-cols-4 gap-3 text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-400 font-medium">Current per L/min</span>
                <span className="font-mono font-bold text-slate-700">
                  {config.plausibility_guard.current_ma_per_leak_lpm} mA
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400 font-medium">Acoustic veto floor</span>
                <span className="font-mono font-bold text-slate-700">
                  {config.plausibility_guard.acoustic_min_residual_lpm} L/min
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400 font-medium">Veto margin</span>
                <span className="font-mono font-bold text-slate-700">
                  {config.plausibility_guard.margin}×
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400 font-medium">Never veto below</span>
                <span className="font-mono font-bold text-slate-700">
                  {config.plausibility_guard.min_residual_lpm} L/min
                </span>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* How detection works — COLLAPSED by default. The dashboard's job is to
          show state; this is here for a reader who wants the method, and it
          should not push the actual readings below the fold to get there. */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl shadow-xs overflow-hidden">
        <button
          type="button"
          onClick={() => setShowExplanations((v) => !v)}
          aria-expanded={showExplanations}
          className="w-full flex items-center justify-between px-6 py-4 text-left hover:bg-slate-50 dark:hover:bg-slate-800/50 transition"
        >
          <span className="text-sm font-bold text-slate-900 dark:text-slate-100 flex items-center space-x-2">
            <Activity className="w-4 h-4 text-blue-600" />
            <span>How detection works</span>
          </span>
          {showExplanations
            ? <ChevronDown className="w-4 h-4 text-slate-400" />
            : <ChevronRight className="w-4 h-4 text-slate-400" />}
        </button>

        {showExplanations && (
          <div className="px-6 pb-6 pt-1 grid grid-cols-1 md:grid-cols-2 gap-x-8 gap-y-5">
            {CHANNEL_EXPLANATIONS.map(({ key, title, body }) => (
              <div key={key} className={key === "fusion" ? "md:col-span-2 md:border-t md:border-slate-100 dark:md:border-slate-800 md:pt-5" : ""}>
                <h4 className="text-[11px] font-bold uppercase tracking-wide text-slate-900 dark:text-slate-200">
                  {title}
                </h4>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1.5 leading-relaxed">
                  {body}
                </p>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};
