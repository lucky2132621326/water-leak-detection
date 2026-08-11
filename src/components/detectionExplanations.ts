/**
 * Plain-language explanation of each detection channel.
 *
 * Kept as data rather than inline JSX so the wording can be reviewed as prose,
 * and so nothing here can accidentally reference a live value — these are
 * descriptions of method, not readings.
 */
export interface ChannelExplanation {
  key: string;
  title: string;
  body: string;
}

export const CHANNEL_EXPLANATIONS: ChannelExplanation[] = [
  {
    key: "mass_balance",
    title: "Mass Balance",
    body:
      "Water is conserved. Q_in minus Q_out should be zero; whatever is missing is leaking. " +
      "Alarms when the residual exceeds k times sigma — the noise standard deviation measured " +
      "during a clean 30-minute run — and stays there for the persistence window. The persistence " +
      "requirement is what suppresses false alarms from air bubbles and transients.",
  },
  {
    key: "current_signature",
    title: "Current Signature",
    body:
      "A leak lowers hydraulic resistance, so flow rises and the pump moves to a different point " +
      "on its head-flow curve, shifting motor current. We do not threshold raw current, which " +
      "varies with supply voltage and duty. We fit an expected-current model from clean data and " +
      "detect on the residual. Physically independent of the flow meters: both could drift " +
      "together without moving this channel.",
  },
  {
    key: "mnf",
    title: "MNF (Minimum Night Flow)",
    body:
      "During a scripted low-demand window, any nonzero inlet flow is by definition leakage. This " +
      "is the method water utilities actually use. Near-zero false positives and immune to sensor " +
      "mismatch, but latency measured in hours rather than seconds.",
  },
  {
    key: "cusum",
    title: "CUSUM",
    body:
      "Accumulates small deviations over time, so it catches slow leaks that never cross the " +
      "3-sigma line but represent a persistent shift in the mean. Fast thresholds miss these " +
      "entirely.",
  },
  {
    key: "acoustic",
    title: "Acoustic",
    body:
      "Water jetting through a leak orifice creates turbulence that vibrates the pipe wall. Leak " +
      "energy concentrates in the 50-150 Hz band, distinct from pump harmonics. Detects on the " +
      "ratio to a clean baseline, not absolute energy, because absolute values depend on sensor " +
      "mounting.",
  },
  {
    key: "acoustic_ml",
    title: "Acoustic ML",
    body:
      "A random forest classifier over spectral features. Instead of one hand-tuned ratio " +
      "threshold, it learns the multi-dimensional boundary between leaking and clean vibration. " +
      "Features are self-normalising by design: spectral_tilt is band_mid divided by band_low, " +
      "two bands from the same sensor at the same instant, so mounting quality and pump duty " +
      "cancel out. Trained on operator-logged leak events with train/test splits grouped by run, " +
      "so near-identical rows from one leak never span both sides.",
  },
  {
    key: "fusion",
    title: "Why Fusion",
    body:
      "Each channel has different failure modes. Flow meters drift. Current shifts with " +
      "temperature. Acoustics pick up pump noise. Agreement across physically independent " +
      "channels is far stronger evidence than any single channel crossing a threshold, so the " +
      "fused confidence weights independent agreement over single-channel magnitude.",
  },
];

/** Display names for the ignition strip, matching the card headings. */
export const CHANNEL_LABELS: Record<string, string> = {
  mass_balance: "Mass Balance",
  Mass_Balance: "Mass Balance",
  current_signature: "Current",
  mnf: "MNF",
  cusum: "CUSUM",
  acoustic: "Acoustic",
  acoustic_ml: "Acoustic ML",
  pressure_drop: "Pressure (sim)",
};
