from backend.pipeline import DetectionPipeline


def test_recombined_branch_is_not_double_subtracted():
    pipeline = DetectionPipeline()
    result = pipeline.process_sample(
        ts=1_754_131_200,
        q_in=5.02,
        q_out=5.0,
        q_branch=1.75,
        current_ma=650.0,
        voltage_v=12.0,
    )

    assert result["hydraulics"]["topology"] == "recombined_branch"
    assert result["hydraulics"]["branch_in_mass_balance"] is False
    assert result["residual"] == 0.0
