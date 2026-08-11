"""Response Builder

Shapes a raw DetectionPipeline result into the output contract the problem
statement requires: a leak likelihood score, a time window, human-readable
evidence, a false-positive/confidence disclaimer, and a work-order summary.
Deliberately excludes any valve/pump control instruction text.
"""
from backend.llm.summary_client import generate_work_order_summary

_DISCLAIMER = (
    "Results are indicative only and require field verification before any "
    "repair action is taken. This system does not issue valve or pump control "
    "instructions."
)

# There is deliberately NO per-tier false-positive rate table here any more.
#
# The old one asserted 1% / 3% / 8% / 20% by confidence tier, citing
# docs/DECISIONS.md #003's "14.2% -> <1.5%" figure. That figure was never
# measured against logged leak events, so the rates were a plausible-looking
# invention presented to an operator as a property of the system — the exact
# failure this codebase has been sweeping for.
#
# A real false-positive rate is computable: score a set of runs against their
# operator-logged leak windows (backend/benchmark/ground_truth.py produces
# precision and a false-alarms-per-hour figure). Until runs exist, the honest
# answer is "not yet measured", and that is what ships.
_FP_RATE_BASIS = (
    "No false-positive rate has been measured for this configuration. A real "
    "figure requires scoring recorded runs against operator-logged leak events "
    "(Analytics -> Benchmark). Confidence tier reflects how much independent "
    "evidence backs this alarm, not an error probability."
)


def _format_time_window(alarm_onset_ts, ts):
    if alarm_onset_ts is None:
        return None
    duration_sec = max(0, ts - alarm_onset_ts)
    return {
        "start_ts": alarm_onset_ts,
        "end_ts": ts,
        "duration_sec": round(duration_sec, 1)
    }


def _build_evidence_text(pipeline_result):
    residual = pipeline_result["residual"]
    active_methods = pipeline_result["fusion"]["active_methods"]
    detectors = {d["method"]: d for d in pipeline_result["detectors"]}

    parts = [f"flow residual {residual:+.2f} L/min ({'above' if residual > 0 else 'at/below'} baseline)"]

    # Acoustic evidence is quoted as a RATIO to this rig's own quiet baseline.
    # An absolute band energy would be meaningless to a reader and would vary
    # with pump duty and mounting; the ratio is the thing that actually means
    # "louder than it should be".
    acoustic = detectors.get("acoustic") or {}
    if acoustic.get("active") and acoustic.get("ratio") is not None:
        parts.append(f"pipe noise {acoustic['ratio']:.2f}x baseline in 50-150 Hz")

    current = detectors.get("current_signature") or {}
    if current.get("residual_ma"):
        parts.append(f"pump current {current['residual_ma']:+.0f} mA vs model")

    ml = detectors.get("acoustic_ml") or {}
    if ml.get("active") and ml.get("probability") is not None:
        # The provenance is inseparable from the number. A synthetic-trained
        # model's probability describes the generator it learned, not this pipe,
        # so the caveat is part of the sentence rather than a footnote.
        marker = " [SYNTHETIC MODEL]" if ml.get("is_synthetic_model") else ""
        parts.append(f"ML leak probability {ml['probability']:.2f}{marker}")

    # Present only in mock — the live detector set has no pressure channel at
    # all, so this branch cannot execute for a real rig. Always "SIMULATED",
    # never "measured" and never "estimated".
    pressure = detectors.get("pressure_drop") or {}
    if pressure.get("active") and pressure.get("pressure_bar") is not None:
        parts.append(f"pressure {pressure['pressure_bar']} bar (SIMULATED)")

    if active_methods:
        parts.append(f"confirmed by {', '.join(active_methods)}")
    else:
        parts.append("no detector currently in alarm")

    if pipeline_result["fusion"].get("suppressed_as_implausible"):
        parts.append("INSTRUMENT FAULT — leak alarm withheld: "
                     + pipeline_result["fusion"]["suppression_reason"])

    return "; ".join(parts)


def build_response(pipeline_result, zone_names=None):
    fusion = pipeline_result["fusion"]
    localization = pipeline_result["localization"]
    tier = pipeline_result["confidence_tier"]

    likelihood_score = round(fusion["fused_score"] * 100, 1)
    time_window = _format_time_window(pipeline_result["alarm_onset_ts"], pipeline_result["ts"])
    evidence_text = _build_evidence_text(pipeline_result)

    evidence_for_summary = {
        "zone": localization.get("zone", "NONE"),
        "likelihood_score": likelihood_score,
        "residual_lpm": pipeline_result["residual"],
        "active_methods": fusion["active_methods"],
        "acoustic_ratio": (next((d for d in pipeline_result["detectors"] if d["method"] == "acoustic"), {}) or {}).get("ratio"),
    }

    detectors_raw = {d["method"]: d for d in pipeline_result["detectors"]}
    pressure_channel = detectors_raw.get("pressure_drop")
    ml_channel = detectors_raw.get("acoustic_ml")

    # Provenance blocks. These exist so the UI physically cannot render a value
    # without the caveat that qualifies it — a badge in a tooltip is a badge
    # nobody reads.
    simulated_channels = {}
    if pressure_channel is not None:
        simulated_channels["pressure_drop"] = {
            "is_simulated": True,
            "notice": pressure_channel.get("simulated_notice"),
        }

    model_provenance = None
    if ml_channel is not None and ml_channel.get("model_note"):
        model_provenance = {
            "channel": "acoustic_ml",
            "note": ml_channel.get("model_note"),
            "is_synthetic": ml_channel.get("is_synthetic_model"),
            "sklearn_warning": ml_channel.get("sklearn_warning"),
        }

    plausibility = pipeline_result.get("plausibility") or {}
    # A withheld alarm is still something the operator must act on — a meter has
    # almost certainly failed. Reporting it as an instrument fault keeps the
    # suppression visible instead of turning a broken sensor into silence.
    sensor_fault = {
        "is_fault": True,
        "hypothesis": plausibility.get("fault_hypothesis"),
        "detail": plausibility.get("reason"),
        "contradicting_channels": plausibility.get("contradicting", []),
    } if fusion.get("suppressed_as_implausible") else None

    is_reportable = pipeline_result["state"]["is_confirmed"]
    work_order = generate_work_order_summary(evidence_for_summary) if is_reportable else None

    # Keyed by method for easy lookup by dashboard components (DetectionEngineView etc).
    detectors_by_method = {d["method"]: d for d in pipeline_result["detectors"]}

    return {
        "ts": pipeline_result["ts"],
        "residual": pipeline_result["residual"],
        "is_alarm": is_reportable,
        "likelihood_score": likelihood_score,
        "confidence_tier": tier,
        "time_window": time_window,
        "zone": localization.get("zone", "NONE"),
        "zone_confidence": localization.get("confidence", "NONE"),
        "evidence": evidence_text,
        "active_methods": fusion["active_methods"],
        "false_positive_warning": {
            "disclaimer": _DISCLAIMER,
            # None, not a number. An explicit empty state beats a plausible
            # placeholder — see _FP_RATE_BASIS.
            "estimated_false_positive_rate": None,
            "basis": _FP_RATE_BASIS,
        },
        "work_order_summary": work_order,
        "sensor_fault": sensor_fault,
        "detectors": detectors_by_method,
        "fusion": {
            "fused_confidence": round(fusion["fused_score"], 2),
            "is_alarm": is_reportable,
            "severity": tier
        },
        "water_c": pipeline_result.get("water_c"),
        "mode": pipeline_result.get("mode"),
        "channels": pipeline_result.get("channels"),
        #: Non-empty only in mock. Keyed by method so a UI can look up the notice
        #: for whatever channel it is about to draw.
        "simulated_channels": simulated_channels,
        #: When each channel crossed its threshold this episode. Lets the UI show
        #: the ignition order across independent physics.
        "channel_crossed_at": pipeline_result.get("channel_crossed_at") or {},
        #: The acoustic_ml bundle's own `note`. Present whenever the channel
        #: exists, so a confidence and its provenance always arrive together.
        "model_provenance": model_provenance,
    }
