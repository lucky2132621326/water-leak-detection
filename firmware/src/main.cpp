// =============================================================================
// Jal Netra — ESP32 sensor node
//
// Publishes the nested telemetry contract in docs/MQTT_SPEC.md (spec Part G) at
// 1 Hz, and accepts pump/servo commands on rig/cmd.
//
// This node MEASURES and REPORTS. It makes no detection decisions — every
// threshold and verdict lives in the Python backend. The one exception is the
// on-device FFT in vibration_sensor.cpp, which exists purely because acoustic
// data cannot be streamed at 1 Hz.
//
// There is no pressure sensor and no leak solenoid on this rig. Leaks are made
// by a human backing off a worm-drive clamp on a tee stub; the software's only
// role is to record when that happened.
// =============================================================================
#include <Arduino.h>
#include <Wire.h>
#include <Adafruit_INA219.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <ESP32Servo.h>

#include "config.h"
#include "mqtt_client.h"
#include "vibration_sensor.h"

// --- pulse counters ----------------------------------------------------------
// Written from ISRs, read from loop(). volatile is necessary but not sufficient:
// a 32-bit read is atomic on this core, so a plain read is safe, but the
// read-and-clear below must not be interrupted mid-way or pulses are lost.
volatile uint32_t pulsesIn = 0, pulsesOut = 0, pulsesBranch = 0;
volatile uint32_t totalIn = 0, totalOut = 0, totalBranch = 0;

void IRAM_ATTR isrFlowIn()     { pulsesIn++;     totalIn++; }
void IRAM_ATTR isrFlowOut()    { pulsesOut++;    totalOut++; }
void IRAM_ATTR isrFlowBranch() { pulsesBranch++; totalBranch++; }

Adafruit_INA219 ina219;
OneWire oneWire(PIN_DS18B20);
DallasTemperature tempSensor(&oneWire);
VibrationSensor vibration;
MQTTHandler mqtt;
Servo branchValve;

bool tempPresent = false;
bool pump1On = false, pump2On = false;
int  servoDeg = SERVO_OPEN_DEG;

uint32_t lastTelemetry = 0;
uint32_t lastCommandMs = 0;
uint32_t pumpStartedMs = 0;
bool     runtimeLockout = false;

// --- pumps -------------------------------------------------------------------
// Relays are ACTIVE-LOW. Every pump state change goes through here so the
// watchdog bookkeeping cannot drift out of sync with the actual relay.
void setPump(int pin, bool on, bool& state) {
    digitalWrite(pin, on ? RELAY_ON : RELAY_OFF);
    state = on;
    if (on && pumpStartedMs == 0) pumpStartedMs = millis();
    if (!pump1On && !pump2On) pumpStartedMs = 0;
}

void stopPumps(const char* reason) {
    digitalWrite(PIN_RELAY_PUMP1, RELAY_OFF);
    digitalWrite(PIN_RELAY_PUMP2, RELAY_OFF);
    pump1On = pump2On = false;
    pumpStartedMs = 0;
    Serial.printf("[SAFETY] pumps stopped: %s\n", reason);
    mqtt.publishStatus(reason);
}

// --- command handling --------------------------------------------------------
void onCommand(bool hasPump1, bool p1, bool hasPump2, bool p2, bool hasServo, int deg) {
    // Any valid command refreshes the watchdog. Losing the network must stop the
    // pumps, so the watchdog is fed by commands rather than by the loop itself.
    lastCommandMs = millis();

    if (runtimeLockout && ((hasPump1 && p1) || (hasPump2 && p2))) {
        Serial.println("[SAFETY] runtime lockout active — explicit reset required");
        mqtt.publishStatus("runtime-lockout");
        return;
    }

    if (hasPump1) setPump(PIN_RELAY_PUMP1, p1, pump1On);
    if (hasPump2) setPump(PIN_RELAY_PUMP2, p2, pump2On);

    if (hasServo) {
        // The MG996R stalls at 1.5-2.5A against the pinch. Held there it browns
        // out the shared rail and corrupts pulse counts — during an isolation
        // test, which is exactly when the readings matter most. So: attach,
        // move, let it settle, detach.
        servoDeg = constrain(deg, SERVO_OPEN_DEG, SERVO_CLOSED_DEG);
        branchValve.attach(PIN_SERVO_BRANCH_A);
        branchValve.write(servoDeg);
        delay(400);
        branchValve.detach();
        Serial.printf("[SERVO] Branch A pinch valve -> %d deg\n", servoDeg);
    }
}

// --- setup -------------------------------------------------------------------
void attachFlowPin(int pin, void (*isr)()) {
    // INPUT, never INPUT_PULLUP. The YF-S201 is open-collector to 5V and the
    // ESP32 is not 5V tolerant, so each line runs through a 10k/20k divider
    // giving ~3.33V at the pin. An internal pull-up would fight the divider,
    // shift the threshold and produce phantom counts.
    pinMode(pin, INPUT);
    attachInterrupt(digitalPinToInterrupt(pin), isr, RISING);
}

void setup() {
    Serial.begin(115200);

    // FIRST, before anything that can block. If WiFi association hangs, the
    // pumps must already be off rather than in whatever state the relay module
    // powers up in.
    pinMode(PIN_RELAY_PUMP1, OUTPUT);
    pinMode(PIN_RELAY_PUMP2, OUTPUT);
    digitalWrite(PIN_RELAY_PUMP1, RELAY_OFF);
    digitalWrite(PIN_RELAY_PUMP2, RELAY_OFF);

    attachFlowPin(PIN_FLOW_IN, isrFlowIn);
    attachFlowPin(PIN_FLOW_OUT, isrFlowOut);
    attachFlowPin(PIN_FLOW_BRANCH, isrFlowBranch);

    Wire.begin(PIN_I2C_SDA, PIN_I2C_SCL);

    if (!ina219.begin()) Serial.println("[WARN] INA219 not found at 0x40");
    if (!vibration.begin()) {
        // Not fatal. The backend marks the acoustic channel inactive and
        // renormalises the fusion weights, so flow and current detection are
        // unaffected.
        Serial.println("[WARN] MPU6050 not found — acoustic channel unavailable");
    }

    tempSensor.begin();
    tempPresent = tempSensor.getDeviceCount() > 0;
    if (!tempPresent) {
        // Almost always the missing 4.7k pull-up to 3V3 rather than a dead probe.
        Serial.println("[WARN] DS18B20 not enumerated — check the 4.7k 1-Wire pull-up");
    }

    ESP32PWM::allocateTimer(0);
    branchValve.setPeriodHertz(50);

    mqtt.begin(onCommand);
    lastCommandMs = millis();
}

// --- telemetry ---------------------------------------------------------------
float toLpm(uint32_t pulses, float k, uint32_t elapsedMs) {
    if (elapsedMs == 0 || k <= 0) return 0.0f;
    // pulses / K = litres; scaled to litres per minute over the actual elapsed
    // interval rather than an assumed one, so a late loop does not inflate flow.
    return ((float)pulses / k) * (60000.0f / (float)elapsedMs);
}

void loop() {
    mqtt.loop();
    const uint32_t now = millis();

    // --- safety interlocks, evaluated every pass and independent of the network
    if ((pump1On || pump2On) && (now - lastCommandMs > PUMP_WATCHDOG_MS)) {
        // No contact for 30 s. A dry-run destroys the pump, so silence must fail
        // safe rather than leave it running unattended.
        stopPumps("watchdog-no-command");
    }
    if (pumpStartedMs != 0 && (now - pumpStartedMs > PUMP_MAX_RUNTIME_MS)) {
        runtimeLockout = true;
        stopPumps("max-runtime-exceeded");
    }

    if (now - lastTelemetry < TELEMETRY_INTERVAL_MS) return;
    const uint32_t elapsed = now - lastTelemetry;
    lastTelemetry = now;

    // Read and clear atomically. An interrupt landing between the read and the
    // reset would drop that pulse, and dropped inlet pulses look exactly like a
    // leak to the mass balance.
    noInterrupts();
    const uint32_t pIn = pulsesIn, pOut = pulsesOut, pBranch = pulsesBranch;
    pulsesIn = pulsesOut = pulsesBranch = 0;
    const uint32_t tIn = totalIn, tOut = totalOut, tBranch = totalBranch;
    interrupts();

    const float qIn     = toLpm(pIn, K1_PULSES_PER_LITRE, elapsed);
    const float qOut    = toLpm(pOut, K2_PULSES_PER_LITRE, elapsed);
    const float qBranch = toLpm(pBranch, K3_PULSES_PER_LITRE, elapsed);

    const float busV      = ina219.getBusVoltage_V();
    const float currentMA = ina219.getCurrent_mA();
    const float powerMW   = ina219.getPower_mW();

    const VibrationSample vib = vibration.read();

    float waterC = NAN;
    if (tempPresent) {
        tempSensor.requestTemperatures();
        waterC = tempSensor.getTempCByIndex(0);
        if (waterC < -100.0f) waterC = NAN;   // DEVICE_DISCONNECTED
    }

    // Publish a real epoch when NTP has synced, and NOTHING otherwise.
    //
    // The previous firmware fell back to millis()/1000 here, putting uptime — a
    // different epoch entirely — into the same field. Nothing downstream could
    // tell, so samples landed in 1970 and, after ~20 hours of uptime, mapped
    // into the 01:00-05:00 window and switched on the night-flow detector for a
    // rig that was not at night. Sending 0 says "I do not know what time it is",
    // which the backend can act on honestly.
    const time_t epoch = time(nullptr);
    const bool clockSynced = epoch > 1700000000;

    mqtt.publishTelemetry(
        clockSynced ? (double)epoch : 0.0, clockSynced,
        qIn, qOut, qBranch, tIn, tOut, tBranch,
        busV, currentMA, powerMW,
        vib, waterC, tempPresent,
        pump1On, pump2On, servoDeg,
        now / 1000);
}
