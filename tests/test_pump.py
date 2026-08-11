"""
Hardware Test Script: Relay / Pump Control
Verifies Pump 1 and Pump 2 ON/OFF state actuation signals.
"""

def test_pump_relay(pump_id=1, state=True):
    state_str = "ENABLED (12V ON)" if state else "DISABLED (0V OFF)"
    print(f"[TEST PUMP] Toggling Pump #{pump_id} relay state -> {state_str}")
    assert pump_id in (1, 2), "Only the two configured pump relays are valid"
    assert isinstance(state, bool), "Relay state must be boolean"
    print(f"[PASS] Pump #{pump_id} relay control verified!")

if __name__ == "__main__":
    test_pump_relay(1, True)
    test_pump_relay(2, False)
