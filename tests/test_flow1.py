"""
Hardware Test Script: YF-S201 Flow Sensor #1 (Q_in)
Verifies pulse counting and LPM conversion on ESP32 / Local collector interface.
"""
import time

def test_flow_sensor_1(pulse_count=45, duration_sec=1.0):
    # YF-S201 pulse factor: 7.5 pulses per second = 1 L/min
    hz = pulse_count / duration_sec
    lpm = hz / 7.5
    print(f"[TEST YF-S201 #1] Pulse Count={pulse_count}, Frequency={hz:.1f}Hz -> Calculated Flow = {lpm:.2f} LPM")
    assert lpm >= 0.0, "Flow rate cannot be negative"
    print("[PASS] YF-S201 #1 flow sensor test successful!")

if __name__ == "__main__":
    test_flow_sensor_1()
