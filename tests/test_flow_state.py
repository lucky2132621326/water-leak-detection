from backend.ingestion.flow_state import derive_water_flow_state


def test_waiting_before_first_sensor_packet():
    state = derive_water_flow_state(None, None, now=100.0)
    assert state["status"] == "waiting"
    assert state["has_sample"] is False
    assert state["is_flowing"] is None
    assert state["sensors"]["flow_1"]["rate_lpm"] is None


def test_detects_water_flow_from_any_flow_sensor():
    latest = {"q_in": 0.0, "q_out": 1.25, "q_branch": 0.0}
    state = derive_water_flow_state(latest, 98.0, now=100.0)
    assert state["status"] == "flowing"
    assert state["is_flowing"] is True
    assert state["sensors"]["flow_2"]["flowing"] is True


def test_tiny_positive_rate_is_displayed_and_counts_as_flowing():
    latest = {"q_in": 0.01, "q_out": 0.01, "q_branch": 0.001}
    state = derive_water_flow_state(latest, 99.0, now=100.0)
    assert state["status"] == "flowing"
    assert state["sensors"]["flow_1"]["rate_lpm"] == 0.01
    assert state["sensors"]["flow_3"]["rate_lpm"] == 0.001


def test_fresh_zero_rates_mean_no_flow():
    latest = {"q_in": 0.0, "q_out": 0.0, "q_branch": 0.0}
    state = derive_water_flow_state(latest, 99.0, now=100.0)
    assert state["status"] == "no_flow"
    assert state["is_flowing"] is False


def test_stale_sample_retains_values_without_claiming_current_flow():
    latest = {"q_in": 2.0, "q_out": 1.9, "q_branch": 0.0}
    state = derive_water_flow_state(latest, 80.0, now=100.0)
    assert state["status"] == "stale"
    assert state["is_flowing"] is None
    assert state["last_known_flowing"] is False
    assert state["sensors"]["flow_1"]["rate_lpm"] == 0.0


def test_zero_packet_holds_last_nonzero_value_for_ten_seconds():
    latest = {"q_in": 0.0, "q_out": 0.0, "q_branch": 0.0}
    history = [
        {"q_in": 1.75, "q_out": 0.0, "q_branch": 0.0, "received_at": 100.0},
        {**latest, "received_at": 105.0},
    ]
    state = derive_water_flow_state(latest, 105.0, history=history, now=106.0)
    sensor = state["sensors"]["flow_1"]
    assert sensor["raw_rate_lpm"] == 0.0
    assert sensor["rate_lpm"] == 1.75
    assert sensor["held"] is True
    assert state["status"] == "flowing"


def test_held_value_becomes_zero_ten_seconds_after_nonzero_packet():
    latest = {"q_in": 0.0, "q_out": 0.0, "q_branch": 0.0}
    history = [
        {"q_in": 1.75, "q_out": 0.0, "q_branch": 0.0, "received_at": 100.0},
        {**latest, "received_at": 105.0},
    ]
    state = derive_water_flow_state(latest, 105.0, history=history, now=110.01)
    sensor = state["sensors"]["flow_1"]
    assert sensor["rate_lpm"] == 0.0
    assert sensor["held"] is False
    assert state["status"] == "no_flow"
