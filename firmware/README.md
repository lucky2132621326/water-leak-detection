# Firmware (ESP32)

Platform: **PlatformIO / Arduino Framework**
Target MCU: **ESP32 DevModule**

## Building & Flashing

```bash
# One-time setup: copy src/secrets.example.h to src/secrets.h and set the
# Wi-Fi SSID/password plus the laptop's LAN IP as MQTT_BROKER.

# Compile and flash via USB serial
pio run --target upload

# Open Serial Monitor (115200 baud)
pio device monitor
```

## Structure
- `src/main.cpp`: Main firmware entry point, timer interrupts, MQTT telemetry publisher.
- `src/config.h`: MQTT topics, calibration constants, and GPIO pin definitions.
- `src/secrets.h`: Local Wi-Fi credentials and MQTT broker IP (Git-ignored).
- `src/flow_sensor.*`: Pulse ISR counting & LPM flow calculations.
- `src/ina219.*`: Pump current & voltage sensor driver.
- `src/mqtt_client.*`: Nested telemetry, retained status/LWT, and supervised command receiver.
- `src/relay.*`: Active-low P1/P2 relay controllers with firmware safety interlocks.
- `src/servo.*`: Branch A pinch-valve servo control.
