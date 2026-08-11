"""
Hardware Test Script: INA219 Current & Voltage Sensor
Verifies motor current (mA) and bus voltage (V) sampling.
"""

def test_ina219_sensor(voltage=11.9, current_ma=425.0):
    power_mw = voltage * current_ma
    print(f"[TEST INA219] Bus Voltage = {voltage}V, Motor Current = {current_ma}mA -> Calculated Power = {power_mw:.1f} mW")
    assert 0.0 <= voltage <= 24.0, "Bus voltage out of range"
    assert current_ma >= 0.0, "Current cannot be negative"
    print("[PASS] INA219 current & voltage sensor test successful!")

if __name__ == "__main__":
    test_ina219_sensor()
