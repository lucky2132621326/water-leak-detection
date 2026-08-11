import React from "react";

/**
 * Shared pieces for showing a detection channel's CHANGE rather than its level.
 *
 * Every channel here works the same way: it compares a current value against a
 * baseline it learned while the rig was quiet. The level on its own says almost
 * nothing — 0.09 of band-mid energy is meaningless without knowing the pipe
 * normally sits at 0.03. The delta is the entire signal, so it gets the emphasis
 * and the baseline is shown beside it as context.
 */

/** How close a channel is to firing. Drives colour consistently everywhere. */
export type DeltaState = "clear" | "approaching" | "exceeded";

/**
 * Fraction of the way to threshold, mapped to a state.
 *
 * "approaching" starts at 60% deliberately: a channel at two-thirds of its
 * threshold is the interesting case a reader should notice *before* it fires,
 * which is the whole point of showing progress rather than a binary.
 */
export function deltaState(progress: number | null | undefined): DeltaState {
  if (progress == null || !isFinite(progress)) return "clear";
  if (progress >= 1) return "exceeded";
  if (progress >= 0.6) return "approaching";
  return "clear";
}

const STATE_TEXT: Record<DeltaState, string> = {
  clear: "text-emerald-600 dark:text-emerald-400",
  approaching: "text-amber-600 dark:text-amber-400",
  exceeded: "text-rose-600 dark:text-rose-400",
};

const STATE_STROKE: Record<DeltaState, string> = {
  clear: "#10b981",
  approaching: "#f59e0b",
  exceeded: "#f43f5e",
};

const fmt = (v: number | null | undefined, digits: number) =>
  v == null || !isFinite(v) ? "—" : v.toFixed(digits);

/**
 * baseline → current, with the delta emphasised underneath.
 *
 * `delta` is passed in rather than derived: each channel expresses its change in
 * its own natural units (sigma multiples, mA and %, a ratio), and flattening
 * that to one formula would lose the meaning.
 */
export const DeltaRow: React.FC<{
  label: string;
  baseline: number | null | undefined;
  current: number | null | undefined;
  unit?: string;
  digits?: number;
  delta: string | null;
  state: DeltaState;
}> = ({ label, baseline, current, unit = "", digits = 3, delta, state }) => (
  <div className="space-y-1">
    <div className="text-[10px] uppercase tracking-wide text-slate-400 font-semibold">{label}</div>
    <div className="flex items-baseline gap-1.5 font-mono text-xs">
      <span className="text-slate-400">{fmt(baseline, digits)}</span>
      <span className="text-slate-300 dark:text-slate-600">→</span>
      <span className="text-slate-900 dark:text-slate-100 font-bold text-sm">
        {fmt(current, digits)}
        {unit && <span className="text-[10px] font-normal text-slate-400 ml-0.5">{unit}</span>}
      </span>
    </div>
    {/* The number a reader should actually take away. */}
    <div className={`font-mono text-sm font-extrabold ${STATE_TEXT[state]}`}>
      {delta ?? "—"}
    </div>
  </div>
);

/**
 * 60-second sparkline, so the *moment* of change is visible rather than inferred
 * from a number that was different a second ago.
 *
 * Deliberately unlabelled and unaxised: it is a shape, not a chart. Scaled to
 * its own min/max so a channel with tiny absolute values still shows its
 * excursion — the alternative, a shared scale, would flatten every channel
 * except the loudest into a straight line.
 */
export const Sparkline: React.FC<{
  points: number[];
  state: DeltaState;
  threshold?: number | null;
  height?: number;
}> = ({ points, state, threshold, height = 28 }) => {
  const usable = points.filter((p) => p != null && isFinite(p));
  if (usable.length < 2) {
    return (
      <div className="h-7 flex items-center text-[10px] text-slate-300 dark:text-slate-600">
        collecting…
      </div>
    );
  }

  const width = 120;
  let min = Math.min(...usable);
  let max = Math.max(...usable);
  // Keep the threshold in frame — a line you cannot see cannot be crossed.
  if (threshold != null && isFinite(threshold)) {
    min = Math.min(min, threshold);
    max = Math.max(max, threshold);
  }
  const span = max - min || 1;
  const y = (v: number) => height - ((v - min) / span) * (height - 4) - 2;
  const x = (i: number) => (i / (usable.length - 1)) * width;

  const path = usable.map((v, i) => `${i === 0 ? "M" : "L"}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const thresholdY = threshold != null && isFinite(threshold) ? y(threshold) : null;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height }} preserveAspectRatio="none">
      {thresholdY != null && (
        <line
          x1={0} x2={width} y1={thresholdY} y2={thresholdY}
          stroke="currentColor" className="text-slate-300 dark:text-slate-600"
          strokeWidth={1} strokeDasharray="3 3"
        />
      )}
      <path d={path} fill="none" stroke={STATE_STROKE[state]} strokeWidth={1.75}
            strokeLinejoin="round" strokeLinecap="round" />
    </svg>
  );
};

/** Fixed-length ring buffer of the last N samples, newest last. */
export function pushSample(buffer: number[], value: number | null | undefined, limit = 60): number[] {
  if (value == null || !isFinite(value)) return buffer;
  const next = [...buffer, value];
  return next.length > limit ? next.slice(next.length - limit) : next;
}
