from backend.localization.localization_service import LocalizationService


def test_branch_b_requires_a_shift_from_learned_baseline():
    service = LocalizationService()
    for _ in range(12):
        service.observe_baseline(1.5)

    normal_branch = service.localize_leak(0.8, q_branch_lpm=1.52, servo_state_deg=0)
    shifted_branch = service.localize_leak(0.8, q_branch_lpm=0.8, servo_state_deg=0)

    assert normal_branch["zone"] == "Main_Trunk"
    assert shifted_branch["zone"] == "Branch_B"


def test_servo_isolation_requires_a_confirmed_residual_drop_not_just_servo_state():
    # Closing the servo alone used to be enough to claim "Branch_A, HIGH" —
    # that's not evidence, it's an actuator-state shortcut. The real signal
    # is whether the residual actually drops once isolated, and only after
    # it's had time to settle.
    service = LocalizationService()

    # Leak present, servo still open: not isolated yet, no verdict on a branch.
    first = service.localize_leak(0.8, q_branch_lpm=1.5, servo_state_deg=0)
    assert first["zone"] == "Main_Trunk"

    # Servo just closed — one sample in, not settled yet, so still no claim.
    just_closed = service.localize_leak(0.8, q_branch_lpm=1.5, servo_state_deg=45)
    assert just_closed["zone"] != "Branch_A"

    # A few more samples with the residual actually gone: isolation confirmed.
    service.localize_leak(0.05, q_branch_lpm=0.1, servo_state_deg=45)
    confirmed = service.localize_leak(0.05, q_branch_lpm=0.1, servo_state_deg=45)
    assert confirmed["zone"] == "Branch_A"
    assert confirmed["confidence"] == "HIGH"
    assert "isolation_test" in confirmed


def test_servo_isolation_that_does_not_drop_residual_does_not_claim_branch_a():
    service = LocalizationService()
    service.localize_leak(0.8, q_branch_lpm=1.5, servo_state_deg=0)
    service.localize_leak(0.8, q_branch_lpm=1.5, servo_state_deg=45)
    service.localize_leak(0.8, q_branch_lpm=1.5, servo_state_deg=45)
    # Residual barely moved even after isolating A and letting it settle —
    # the leak isn't in Branch A.
    result = service.localize_leak(0.78, q_branch_lpm=1.5, servo_state_deg=45)
    assert result["zone"] != "Branch_A"


def test_branch_c_is_not_a_valid_localization_output():
    # The rig has no sensor that can distinguish leak tee C from A/B/the main
    # line — see the module docstring. It must never appear as a candidate.
    service = LocalizationService()
    assert "Branch_C" not in service.known_zones
