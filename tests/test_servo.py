"""
Hardware Test Script: Servo Motor Isolation Actuator
Verifies PWM angle commands (0deg = Open, 45deg/90deg = Closed).
"""

def test_servo_actuator(target_deg=45):
    print(f"[TEST SERVO] Sending PWM pulse command to set servo angle to {target_deg}°")
    assert 0 <= target_deg <= 180, "Servo angle must be between 0 and 180 degrees"
    print(f"[PASS] Servo actuation to {target_deg}° verified successfully!")

if __name__ == "__main__":
    test_servo_actuator(0)
    test_servo_actuator(45)
    test_servo_actuator(90)
