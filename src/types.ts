export interface TelemetrySample {
  ts: number;
  q_in: number;
  q_out: number;
  q_branch: number;
  current_ma: number | null;
  bus_v: number | null;
  residual: number;
  /** Acoustic band energies. null when no MPU6050 / piezo is fitted — which is
   *  a different fact from zero, and must not be rendered as a reading. */
  band_mid: number | null;
  vib_rms: number | null;
  piezo_rms: number | null;
  water_c: number | null;
  /** GROUND TRUTH: an operator-logged clamp is open right now. Never the
   *  detector's opinion — that is what makes "detector says clear while a clamp
   *  is open" an honest thing for the dashboard to show. */
  leak_active: boolean;
  pump_on: boolean;
  pump2_on: boolean;
  servo_deg: number;
}

export interface DetectorOutput {
  method: string;
  residual?: number;
  threshold?: number;
  current_ma?: number;
  current_delta_ma?: number;
  score?: number;
  is_alarm: boolean;
  confidence: number;
}

export interface DetectionEval {
  ts: number;
  latest_sample: TelemetrySample;
  detectors: {
    mass_balance: DetectorOutput;
    current_signature: DetectorOutput;
    mnf: DetectorOutput;
    acoustic: DetectorOutput;
    cusum: DetectorOutput;
  };
  fusion: {
    fused_confidence: number;
    is_alarm: boolean;
    severity: string;
  };
}

export interface ReplayRun {
  run_id: string;
  operator: string;
  date: string;
  leak_size_lpm: number;
  location: string;
  duration_sec: number;
  f1_score: number;
  precision: number;
  recall: number;
  latency_sec: number;
}

export interface WorkOrder {
  id: string;
  leak_event_id: number;
  location_node: string;
  severity_lpm: number;
  priority: string;
  assigned_crew: string;
  scheduled_start: string;
  estimated_hrs: number;
  status: string;
}

export interface FileNode {
  name: string;
  path: string;
  type: "file" | "directory";
  children?: FileNode[];
}

// --- Impact analysis (backend/impact/*) -------------------------------------

export type SeverityLabel = "NONE" | "MINOR" | "MODERATE" | "MAJOR" | "CRITICAL";
export type UrgencyLabel = "NONE" | "MONITOR" | "SCHEDULED" | "URGENT" | "IMMEDIATE";

export interface Equivalents {
  basis_litres: number;
  water_tanks: number;
  tank_size_litres: number;
  people_daily_supply: number;
  person_daily_litres: number;
  buckets: number;
  bucket_size_litres: number;
}

export interface WaterLoss {
  leak_rate_lpm: number;
  litres_per_hour: number;
  litres_per_day: number;
  litres_per_week: number;
  litres_per_month: number;
  litres_per_year: number;
  equivalents: Equivalents;
}

export interface CostBreakdown {
  currency_symbol: string;
  rate_per_kilolitre: number;
  cost_per_hour: number;
  cost_per_day: number;
  cost_per_week: number;
  cost_per_month: number;
  cost_per_year: number;
}

export interface SeverityBand {
  label: string;
  min_lpm: number;
  max_lpm: number | null;
}

export interface Severity {
  label: SeverityLabel;
  color: string;
  emoji: string;
  rank: number;
  leak_rate_lpm: number;
  band_description: SeverityBand[];
}

export interface Recommendation {
  urgency: UrgencyLabel;
  headline: string;
  action: string;
  repair_within_days: number | null;
}

export interface ProgressionPoint {
  label: string;
  days: number;
  litres: number;
  cost: number;
  fill_ratio: number;
}

export interface Progression {
  leak_rate_lpm: number;
  repair_delay_days: number;
  delay_options_days: number[];
  timeline: ProgressionPoint[];
  at_repair_delay: { days: number; litres: number; cost: number; equivalents: Equivalents };
  currency_symbol: string;
  assumptions: string;
}

export interface ImpactAnalysis {
  leak_rate_lpm: number;
  water_loss: WaterLoss;
  cost: CostBreakdown;
  severity: Severity;
  recommendation: Recommendation;
  progression: Progression;
  disclaimer: string;
}

/** Compact impact form embedded in telemetry responses and alert rows. */
export interface ImpactSummary {
  leak_rate_lpm: number;
  litres_per_day: number;
  litres_per_month: number;
  cost_per_day: number;
  cost_per_month: number;
  cost_per_year: number;
  currency_symbol: string;
  severity: SeverityLabel;
  severity_color: string;
  urgency: UrgencyLabel;
}

export interface ImpactConfig {
  currency_symbol: string;
  rate_per_kilolitre: number;
  severity_bands: SeverityBand[];
  delay_options_days: number[];
  default_delay_days: number;
  equivalents: Record<string, number>;
}

// --- Alert Center (backend/alerts/*) ----------------------------------------

export type AlertStatus = "ACTIVE" | "RESOLVED" | "FALSE_POSITIVE";

/** backend/llm/summary_client.py returns the text plus which path produced it. */
export interface WorkOrderSummary {
  summary: string;
  source: "llm" | "template";
}

export interface LeakAlert {
  alert_id: string;
  seq: number;
  source: "live" | "mock";
  run_id: string | null;
  status: AlertStatus;
  is_open: boolean;
  zone: string;
  confidence_tier: string;
  likelihood_score: number;
  start_ts: number;
  last_seen_ts: number;
  end_ts: number | null;
  duration_sec: number;
  sample_count: number;
  leak_rate_lpm: number;
  peak_leak_rate_lpm: number;
  evidence: string;
  active_methods: string[];
  false_positive_warning?: { disclaimer: string; estimated_false_positive_rate: number };
  work_order_summary?: WorkOrderSummary | null;
  impact: ImpactSummary;
  created_at: number;
  resolved_at: number | null;
  resolution_note: string | null;
  water_saved_litres: number;
  cost_saved: number;
  savings_horizon_days?: number;
}

export interface AlertCounts {
  total: number;
  active: number;
  resolved: number;
  false_positive: number;
  open_now: number;
}

export interface AlertTimelineBucket {
  month: string;
  total: number;
  resolved: number;
  false_positive: number;
  active: number;
}

export interface AlertsSummary {
  counts: AlertCounts;
  zones: string[];
  timeline: AlertTimelineBucket[];
}

export interface SavingsSummary {
  leaks_prevented: number;
  water_saved_litres: number;
  money_saved: number;
  currency_symbol: string;
  false_positives: number;
  total_alerts: number;
  detection_precision: number | null;
  horizon_days: number;
  equivalents: Equivalents;
  basis: string;
}

// --- Automatic experiment reports (backend/reports/*) -----------------------

export interface ReportLeakEvent {
  location_node: string;
  severity_lpm: number;
  start_ts: number | null;
  stop_ts: number | null;
  start_offset_sec: number | null;
  duration_sec: number | null;
  is_ground_truth: boolean;
  notes: string;
  impact: ImpactSummary;
  volume_lost_litres: number | null;
}

export interface ExperimentReport {
  run_id: string;
  error?: string;
  generated_at: number;
  generated_at_human: string;
  info: {
    run_id: string;
    operator: string;
    date: string;
    duration_sec: number;
    sample_count: number;
    pump_mode: string;
    location: string;
    notes: string;
    start_ts: number;
    end_ts: number;
  };
  leak_events: ReportLeakEvent[];
  metrics: {
    precision?: number;
    recall?: number;
    f1_score?: number;
    true_positives?: number;
    false_positives?: number;
    false_negatives?: number;
    true_negatives?: number;
    avg_latency_sec?: number | null;
  };
  impact: ImpactAnalysis;
  conclusions: string[];
  disclaimer: string;
}


// --- Operating modes ---------------------------------------------------------

/** Exactly two. They differ only in where telemetry originates; everything
 *  after ingestion is one shared pipeline. */
export type OperatingMode = "mock" | "live";

export interface RuntimeCapabilities {
  audience: "operator" | "judge";
  read_only: boolean;
  mutations_allowed: boolean;
}

export interface ScenarioSummary {
  id: string;
  name: string;
  description: string;
  scoreable: boolean;
  duration_sec: number;
  leak_count: number;
  fault_count: number;
  max_leak_lpm: number;
  start_time: string | null;
  demand_mode: "steady" | "variable";
  emits_vibration: boolean;
  emits_piezo: boolean;
  expect_detection: boolean;
  expect_zone: string | null;
}

export interface ScenarioRunResult {
  success: boolean;
  scenario_id: string;
  scenario_name: string;
  run_id: string;
  samples: number;
  verdict: string;
  persisted: boolean;
  metrics: {
    true_positives: number; false_positives: number;
    false_negatives: number; true_negatives: number;
    precision: number | null; recall: number | null;
    f1_score: number | null; detection_latency_sec: number | null;
  };
  expected: { expect_detection: boolean; expect_zone: string | null };
}

export interface ModeState {
  mode: OperatingMode;
  modes: OperatingMode[];
  source: {
    source: string; running: boolean;
    scenario?: ScenarioSummary; speed?: number; loop?: boolean;
    broker?: string; topic?: string;
  };
  sample_count: number;
  rejected_count: number;
}
