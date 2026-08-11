"""Scenario Scorer — grade a mock scenario without touching the database.

`BenchmarkScorer` scores a *stored* run and therefore needs MongoDB. That makes
it unusable as a regression test, which is why the scenario pass rate once lived
in a handoff note rather than in CI, and why a fusion change could silently undo
a scenario fix.

This scores a `ScenarioSpec` straight through the production `DetectionPipeline`,
in memory. Scenarios are seeded, so the numbers are reproducible sample-for-sample
and can be asserted on.

Ground truth comes from the scenario's leak windows via `GroundTruthScorer` — the
same time-window logic that scores a live run against operator-logged clamp
openings. The two paths must agree, because mock exists to validate the code that
will run on hardware.
"""
from backend.benchmark.ground_truth import GroundTruthScorer
from backend.mock.generator import MockTelemetryGenerator
from backend.models.telemetry import TelemetryDTO
from backend.pipeline import DetectionPipeline


def score_scenario(spec, step_sec: float = 1.0, grace: float = None) -> dict:
    # The scenario's own clock anchor, never a fixed 0.0. An epoch of 0 resolves
    # to just outside the MNF night window, which silently disabled that detector
    # and let `night_flow` — the one scenario built to exercise it — pass on the
    # strength of the others while MNF was never evaluated at all.
    generator = MockTelemetryGenerator(spec)
    pipeline = DetectionPipeline()
    scorer = GroundTruthScorer(generator.ground_truth_events(), grace=grace)

    zone_votes = {}
    suppressed_samples = 0

    t = 0.0
    while t <= spec.duration_sec:
        payload = generator.sample_at(t)
        # Parse through the real DTO so mock data traverses the same contract as
        # live data — a schema mistake must break mock too, not only hardware.
        dto = TelemetryDTO.from_dict(payload)

        result = pipeline.process_sample(
            ts=dto.ts,
            q_in=dto.flow.q_in_lpm,
            q_out=dto.flow.q_out_lpm,
            q_branch=dto.flow.q_branch_lpm,
            current_ma=dto.power.current_ma,
            bus_v=dto.power.bus_v,
            pump_on=dto.actuators.pump1,
            servo_state_deg=dto.actuators.servo_deg,
            vibration=dto.vibration,
            water_c=dto.temp.water_c,
        )

        alarm = result["state"]["is_confirmed"]
        scorer.observe(dto.ts, alarm)

        if result["fusion"]["suppressed_as_implausible"]:
            suppressed_samples += 1
        if alarm:
            zone = result["localization"]["zone"]
            zone_votes[zone] = zone_votes.get(zone, 0) + 1

        t += step_sec

    metrics = scorer.summary()
    metrics.update({
        "scenario_id": spec.id,
        "samples": scorer.tp + scorer.fp + scorer.fn + scorer.tn,
        "detected_zone": max(zone_votes, key=zone_votes.get) if zone_votes else None,
        "expected_zone": spec.expect_zone,
        "expect_detection": spec.expect_detection,
        "demand_mode": spec.demand_mode,
        "implausible_samples": suppressed_samples,
    })
    return metrics


def verdict(scored: dict) -> tuple:
    """Reduce a score to pass/fail plus the reason, using the scenario's own
    expectation. Returns (passed, reason)."""
    if not scored["expect_detection"]:
        # A no-leak scenario is graded solely on silence.
        if scored["false_positives"]:
            return False, (f"{scored['false_positives']} false positives on a no-leak scenario "
                           f"({scored['false_alarms_per_hour']}/hour)")
        return True, "silent, as expected"

    if scored["leaks_detected"] == 0:
        return False, "leak never detected"
    if scored["precision"] < 0.8:
        return False, f"precision {scored['precision']} below 0.8"
    if scored["expected_zone"] and scored["detected_zone"] != scored["expected_zone"]:
        return False, (f"localized to {scored['detected_zone']}, "
                       f"expected {scored['expected_zone']}")
    return True, (f"detected at {scored['recall']:.0%} recall, "
                  f"{scored['detection_latency_sec']}s latency")
