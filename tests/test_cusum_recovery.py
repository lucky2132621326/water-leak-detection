from backend.detectors.cusum_detector import CUSUMDetector


def test_cusum_rearms_after_stable_normal_flow():
    detector = CUSUMDetector(slack_k=0.15, decision_h=3.0, reset_after_normal_samples=5)

    for _ in range(5):
        alarm = detector.analyze(1.0)
    assert alarm["is_alarm"] is True

    for _ in range(5):
        recovered = detector.analyze(0.02)

    assert recovered["cusum_score"] == 0.0
    assert recovered["is_alarm"] is False


def test_cusum_normal_window_must_be_consecutive():
    detector = CUSUMDetector(slack_k=0.15, decision_h=1.0, reset_after_normal_samples=3)
    detector.analyze(1.0)
    detector.analyze(1.0)
    detector.analyze(0.0)
    detector.analyze(0.0)
    interrupted = detector.analyze(0.5)

    assert interrupted["recovery_samples"] == 0
    assert interrupted["cusum_score"] > 0
