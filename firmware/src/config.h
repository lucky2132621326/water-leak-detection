#ifndef CONFIG_H
#define CONFIG_H

// Local network credentials are intentionally kept out of source control.
// Copy secrets.example.h to secrets.h and set the rig Wi-Fi + broker address.
#include "secrets.h"

// MQTT Configuration
#define MQTT_PORT 1883
#define MQTT_TOPIC_TELEMETRY "rig/telemetry"
#define MQTT_TOPIC_CMD "rig/cmd"
#define MQTT_TOPIC_STATUS "rig/status"
#define DEVICE_ID "esp32-rig-01"

// GPIO Pinout (see docs/HARDWARE_SETUP.md and firmware/docs/PINOUT.md — README.md's
// table is stale/wrong, do not wire from it)
#define PIN_FLOW_IN 34
#define PIN_FLOW_OUT 35
#define PIN_FLOW_BRANCH 32
#define PIN_RELAY_PUMP 25
#define PIN_RELAY_PUMP2 26
#define PIN_SERVO_LEAK 27
#define PIN_I2C_SDA 21
#define PIN_I2C_SCL 22

// Sensor Calibration Constants
#define K_FACTOR_FLOW_IN 450.0f
#define K_FACTOR_FLOW_OUT 450.0f
#define K_FACTOR_FLOW_BRANCH 450.0f

// Local safety interlocks remain active even if Wi-Fi/MQTT disconnects.
#define COMMAND_WATCHDOG_MS 30000UL
#define MAX_CONTINUOUS_PUMP_RUNTIME_MS 600000UL

// No physical pressure sensor is installed on this rig. pressure_bar is
// intentionally omitted from the telemetry payload; the backend derives an
// estimated value from flow/pump state instead (see backend/utils/pressure_estimate.py).

#endif // CONFIG_H
