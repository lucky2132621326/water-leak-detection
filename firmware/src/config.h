#ifndef CONFIG_H
#define CONFIG_H

// =============================================================================
// Jal Netra — ESP32 sensor node configuration
//
// Pin allocation is authoritative (spec Part C). Cross-check firmware/docs/
// PINOUT.md before changing anything here; a wrong pin on this board is not a
// compile error, it is a silent wrong reading or a bricked flash chip.
// =============================================================================

// --- WiFi / MQTT -------------------------------------------------------------
// Copy secrets.example.h to secrets.h. The real file is git-ignored so rig
// credentials cannot be exposed through the repository or judge dashboard.
#include "secrets.h"

#ifndef MQTT_USERNAME
#define MQTT_USERNAME ""
#endif
#ifndef MQTT_PASSWORD
#define MQTT_PASSWORD ""
#endif

#define WIFI_PASSWORD   WIFI_PASS
#define MQTT_HOST       MQTT_BROKER
#define MQTT_PORT       1883
#define DEVICE_ID       "esp32-rig-01"

#define TOPIC_TELEMETRY "rig/telemetry"
#define TOPIC_CMD       "rig/cmd"
#define TOPIC_STATUS    "rig/status"      // retained, with Last Will

// --- GPIO (spec Part C) ------------------------------------------------------
//
// NEVER USE: GPIO 6-11  (SPI flash — using them bricks the board)
//            GPIO 0/2/12/15 (boot straps)
//
// 34/35 are input-only. All three flow pins are fed from a 10k/20k divider
// (YF-S201 is open-collector to 5V and the ESP32 is NOT 5V tolerant), so
// INTERNAL PULL-UPS MUST STAY OFF — see attachFlowPin() in main.cpp.
#define PIN_FLOW_IN      34    // Flow 1, Q_in
#define PIN_FLOW_OUT     35    // Flow 2, Q_out
#define PIN_FLOW_BRANCH  32    // Flow 3, Q_branch (Branch B)

// Physically wired SDA->D22, SCL->D21 on this rig (swapped from the original
// spec's SDA=21/SCL=22) — matched here rather than re-wiring the board.
#define PIN_I2C_SDA      22    // INA219 @ 0x40, MPU6050 @ 0x68
#define PIN_I2C_SCL      21

// Relays are ACTIVE-LOW: digitalWrite(pin, LOW) energizes the coil and runs the
// pump. Both are driven HIGH at boot, before WiFi, so a rig that never connects
// is not left pumping.
#define PIN_RELAY_PUMP1  25    // P1 — supply pump
#define PIN_RELAY_PUMP2  26    // P2 — demand generator
#define RELAY_ON         LOW
#define RELAY_OFF        HIGH

// MG996R pinch valve on Branch A. Used ONLY for step-test isolation, on
// explicit command. It never creates a leak: leaks are made by a human opening
// a worm-drive clamp on a tee stub.
#define PIN_SERVO_BRANCH_A 27
#define SERVO_OPEN_DEG     0
#define SERVO_CLOSED_DEG   90
// MG996R stall current is 1.5-2.5A. Holding it against the stop browns out the
// sensor rail and corrupts pulse counts at exactly the moment an isolation test
// is running, so it is detached after every move.
#define SERVO_SETTLE_MS    15000

#define PIN_PIEZO        33    // ADC1 — safe to read while WiFi is active
#define PIN_DS18B20      4     // 1-Wire; will NOT enumerate without a 4.7k pull-up to 3V3

// --- Flow calibration --------------------------------------------------------
// YF-S201 nominal is ~450 pulses/litre (f ≈ 7.5 * Q). Per-unit variation is
// significant, so each sensor carries its own volumetrically-measured K. These
// are STARTING values — recalibrate against a measuring cylinder and update.
// The backend stores raw pulse counts alongside the converted rates, so a
// corrected K can be replayed over historical runs without re-running them.
#define K1_PULSES_PER_LITRE 450.0f
#define K2_PULSES_PER_LITRE 450.0f
#define K3_PULSES_PER_LITRE 450.0f

// --- Acoustic sampling (spec Part E.4) ---------------------------------------
// Bursts, not a stream: acoustic data cannot be published at 1 Hz. The on-device
// FFT is BANDWIDTH REDUCTION only — every threshold and decision lives in the
// Python backend.
#define VIB_SAMPLE_COUNT   512
#define VIB_SAMPLE_RATE_HZ 500
// DLPF is configured for ~260 Hz bandwidth so content above Nyquist (250 Hz)
// cannot alias down into the leak band and masquerade as a leak.
#define VIB_BAND_LOW_HZ    10
#define VIB_BAND_MID_LO_HZ 50     // 50-150 Hz — leak jet energy lives here
#define VIB_BAND_MID_HI_HZ 150
#define VIB_BAND_HIGH_HZ   250

#define PIEZO_SAMPLE_RATE_HZ 2000
#define PIEZO_SAMPLE_MS      250
#define PIEZO_SAMPLE_COUNT   ((PIEZO_SAMPLE_RATE_HZ * PIEZO_SAMPLE_MS) / 1000)

// --- Safety interlocks (spec Part H) — must not depend on the network --------
// No command for this long and both pumps stop. A dry-run destroys the pump, so
// losing WiFi must fail safe rather than leaving it running unattended.
#define PUMP_WATCHDOG_MS       30000UL
// Hard cap on continuous running. Clearing it requires an explicit operator
// re-enable, so an unattended rig cannot run itself dry overnight.
#define PUMP_MAX_RUNTIME_MS    3600000UL

#define TELEMETRY_INTERVAL_MS  1000

#endif  // CONFIG_H
