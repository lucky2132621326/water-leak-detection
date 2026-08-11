import type { AlertStatus, SeverityLabel, UrgencyLabel } from "../types";

/**
 * Severity/urgency presentation, kept in one place so a MAJOR leak looks
 * identical on the dashboard, in the alert list, and in the simulator.
 *
 * Class strings are written out in full rather than composed (`bg-${c}-100`)
 * because Tailwind scans source text statically — interpolated class names are
 * never emitted into the stylesheet.
 */
export const SEVERITY_STYLE: Record<SeverityLabel, {
  badge: string; dot: string; text: string; bar: string; ring: string; emoji: string; label: string;
}> = {
  NONE: {
    badge: "bg-slate-100 text-slate-600 border-slate-200",
    dot: "bg-slate-400", text: "text-slate-600", bar: "bg-slate-300",
    ring: "border-slate-200", emoji: "⚪", label: "No Loss",
  },
  MINOR: {
    badge: "bg-emerald-100 text-emerald-700 border-emerald-200",
    dot: "bg-emerald-500", text: "text-emerald-600", bar: "bg-emerald-500",
    ring: "border-emerald-200", emoji: "🟢", label: "Minor",
  },
  MODERATE: {
    badge: "bg-amber-100 text-amber-700 border-amber-200",
    dot: "bg-amber-500", text: "text-amber-600", bar: "bg-amber-500",
    ring: "border-amber-200", emoji: "🟡", label: "Moderate",
  },
  MAJOR: {
    badge: "bg-orange-100 text-orange-700 border-orange-200",
    dot: "bg-orange-500", text: "text-orange-600", bar: "bg-orange-500",
    ring: "border-orange-200", emoji: "🟠", label: "Major",
  },
  CRITICAL: {
    badge: "bg-rose-100 text-rose-700 border-rose-200",
    dot: "bg-rose-500", text: "text-rose-600", bar: "bg-rose-500",
    ring: "border-rose-200", emoji: "🔴", label: "Critical",
  },
};

export const URGENCY_STYLE: Record<UrgencyLabel, { badge: string; text: string }> = {
  NONE:      { badge: "bg-slate-100 text-slate-600 border-slate-200", text: "text-slate-600" },
  MONITOR:   { badge: "bg-sky-100 text-sky-700 border-sky-200", text: "text-sky-700" },
  SCHEDULED: { badge: "bg-amber-100 text-amber-700 border-amber-200", text: "text-amber-700" },
  URGENT:    { badge: "bg-orange-100 text-orange-700 border-orange-200", text: "text-orange-700" },
  IMMEDIATE: { badge: "bg-rose-600 text-white border-rose-700", text: "text-rose-700" },
};

export const STATUS_STYLE: Record<AlertStatus, { badge: string; label: string }> = {
  ACTIVE:         { badge: "bg-rose-100 text-rose-700 border-rose-200", label: "Active" },
  RESOLVED:       { badge: "bg-emerald-100 text-emerald-700 border-emerald-200", label: "Resolved" },
  FALSE_POSITIVE: { badge: "bg-slate-200 text-slate-700 border-slate-300", label: "False Alert" },
};

export function severityStyle(label?: string) {
  return SEVERITY_STYLE[(label as SeverityLabel) ?? "NONE"] ?? SEVERITY_STYLE.NONE;
}

export function urgencyStyle(label?: string) {
  return URGENCY_STYLE[(label as UrgencyLabel) ?? "NONE"] ?? URGENCY_STYLE.NONE;
}

export function statusStyle(label?: string) {
  return STATUS_STYLE[(label as AlertStatus) ?? "ACTIVE"] ?? STATUS_STYLE.ACTIVE;
}

/** Compact litre formatting — big numbers become 26.8k / 1.2M so cards don't wrap. */
export function formatLitres(litres: number | null | undefined, opts: { compact?: boolean } = {}): string {
  const v = Number(litres ?? 0);
  if (!Number.isFinite(v)) return "—";
  if (opts.compact) {
    if (Math.abs(v) >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M L`;
    if (Math.abs(v) >= 10_000) return `${(v / 1000).toFixed(1)}k L`;
  }
  return `${v.toLocaleString(undefined, { maximumFractionDigits: v < 10 ? 2 : 0 })} L`;
}

export function formatMoney(amount: number | null | undefined, symbol = "₹", opts: { compact?: boolean } = {}): string {
  const v = Number(amount ?? 0);
  if (!Number.isFinite(v)) return "—";
  // Normalize records written before Windows config files were read explicitly as UTF-8.
  const normalizedSymbol = symbol === "\u00e2\u201a\u00b9" ? "\u20b9" : symbol;
  if (opts.compact && Math.abs(v) >= 100_000) return `${normalizedSymbol}${(v / 100_000).toFixed(2)}L`;
  if (opts.compact && Math.abs(v) >= 10_000) return `${normalizedSymbol}${(v / 1000).toFixed(1)}k`;
  return `${normalizedSymbol}${v.toLocaleString(undefined, { minimumFractionDigits: v < 100 ? 2 : 0, maximumFractionDigits: v < 100 ? 2 : 0 })}`;
}

export function formatRate(lpm: number | null | undefined): string {
  const v = Number(lpm ?? 0);
  return Number.isFinite(v) ? `${v.toFixed(2)} L/min` : "—";
}

export function formatDuration(seconds: number | null | undefined): string {
  const s = Math.max(0, Math.round(Number(seconds ?? 0)));
  if (!Number.isFinite(s)) return "—";
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ${s % 60}s`;
  const h = Math.floor(m / 60);
  return `${h}h ${m % 60}m`;
}

/** Backend timestamps are epoch *seconds*. */
export function formatTimestamp(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleString(undefined, {
    year: "numeric", month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export function formatDate(ts: number | null | undefined): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString(undefined, { year: "numeric", month: "short", day: "2-digit" });
}
