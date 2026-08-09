export interface TelemetrySample {
  ts: number;
  q_in: number;
  q_out: number;
  q_branch: number;
  current_ma: number;
  voltage_v: number;
  pressure_bar: number;
  residual: number;
  leak_active: boolean;
  pump_on?: boolean;
  pump1_on?: boolean;
  pump2_on?: boolean;
  servo_deg?: number;
  device_id?: string;
  ts_source?: "device_ntp" | "server_received" | "logged";
}

export interface DeviceHealth {
  online: boolean;
  device_id: string;
  last_seen_ts: number | null;
  last_seen_age_sec: number | null;
  uptime_sec: number | null;
  wifi_rssi: number | null;
  heap_free: number | null;
  samples_received: number;
}

export interface SystemHealth {
  status: "ok" | "degraded" | "error";
  mode: "live" | "replay";
  mqtt_connected: boolean;
  database_connected: boolean;
  telemetry_records: number;
  data_source_ready: boolean;
  simulation_mode: boolean;
  replay_run_id: string | null;
  timestamp: number;
  device: DeviceHealth;
  message?: string;
}

export interface TelemetryEnvelope {
  mode: "live" | "replay";
  latest: TelemetrySample | null;
  pump_on: boolean;
  pump1_on?: boolean;
  pump2_on?: boolean;
  leak_active: boolean;
  evaluation: any | null;
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
