from backend.pipeline import DetectionPipeline
from backend.models.telemetry import FlowData, PowerData, TelemetryDTO


def test_recombined_branch_is_not_double_subtracted():
    pipeline = DetectionPipeline()
    result = pipeline.process_sample(TelemetryDTO(
        ts=1_754_131_200,
        seq=1,
        flow=FlowData(q_in_lpm=5.02, q_out_lpm=5.0, q_branch_lpm=1.75),
        power=PowerData(bus_v=12.0, current_ma=650.0),
    ))

    assert result["hydraulics"]["topology"] == "recombined_branch"
    assert result["hydraulics"]["branch_in_mass_balance"] is False
    assert result["residual"] == 0.0
