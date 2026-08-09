from backend.localization.localization_service import LocalizationService


def test_branch_b_requires_a_shift_from_learned_baseline():
    service = LocalizationService()
    for _ in range(12):
        service.observe_baseline(1.5)

    normal_branch = service.localize_leak(0.8, q_branch_lpm=1.52, servo_state_deg=0)
    shifted_branch = service.localize_leak(0.8, q_branch_lpm=0.8, servo_state_deg=0)

    assert normal_branch["zone"] == "Main_Trunk"
    assert shifted_branch["zone"] == "Branch_B"


def test_servo_isolation_identifies_branch_a():
    service = LocalizationService()
    result = service.localize_leak(0.8, q_branch_lpm=1.5, servo_state_deg=45)
    assert result == {"zone": "Branch_A", "confidence": "HIGH"}
