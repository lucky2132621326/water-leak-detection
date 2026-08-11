# HARDWARE SETUP & PINOUT

## ESP32 DevKit V1 Pinout Mapping

| Component | Pin / GPIO | Description |
| :--- | :--- | :--- |
| **Flow Sensor 1 (Inlet)** | GPIO 34 | Hall Effect Pulse (Input Interrupt) |
| **Flow Sensor 2 (Outlet)** | GPIO 35 | Hall Effect Pulse (Input Interrupt) |
| **Flow Sensor 3 (Branch)** | GPIO 32 | Hall Effect Pulse (Input Interrupt) |
| **INA219 Current/Voltage** | GPIO 21 (SDA), GPIO 22 (SCL) | I2C Bus @ 400kHz |
| **Pump P1 Relay** | GPIO 25 | Active-low supply-pump control |
| **Pump P2 Relay** | GPIO 26 | Active-low demand-pump control |
| **Branch A Pinch Servo** | GPIO 27 | PWM control (50Hz) |

## Power Wiring
- **5V DC Line**: Powers ESP32, Relays, and Servo Motor (Separate 5V 3A Power Supply).
- **12V DC Line**: Powers both 12V water pumps.
- **Common Ground**: All DC grounds tied together at main distribution bus.
