#include <Arduino.h>
#include <Preferences.h>
#include "config.h"
#include "flow_sensor.h"
#include "ina219.h"
#include "mqtt_client.h"
#include "relay.h"
#include "servo.h"
#include "vibration_sensor.h"
#include "piezo_sensor.h"
#include "temp_sensor.h"

FlowSensor flowIn(PIN_FLOW_IN, K_FACTOR_FLOW_IN);
FlowSensor flowOut(PIN_FLOW_OUT, K_FACTOR_FLOW_OUT);
FlowSensor flowBranch(PIN_FLOW_BRANCH, K_FACTOR_FLOW_BRANCH);
INA219Sensor powerMeter;
MQTTHandler mqtt;
RelayController pump1Relay(PIN_RELAY_PUMP);
RelayController pump2Relay(PIN_RELAY_PUMP2);
ServoController branchServo(PIN_SERVO_LEAK);
Preferences calibrationPreferences;
VibrationSensor vibrationSensor;
PiezoSensor piezoSensor;
TempSensor tempSensor(PIN_DS18B20);

unsigned long lastTelemetryTime = 0;
unsigned long lastStatusTime = 0;
unsigned long lastCommandTime = 0;
unsigned long lastVibrationBurstTime = 0;
unsigned long pump1StartedAt = 0;
unsigned long pump2StartedAt = 0;
uint32_t telemetrySequence = 0;

// Cached between bursts (spec 5.3: bursts run on a slower cadence than the
// 1Hz telemetry loop). vibrationValid stays false — and the field is
// omitted from the published payload entirely — until the first real burst
// completes, rather than publishing a misleading all-zeros reading.
VibrationSample lastVibration = {false, 0.0f, 0.0f, 0.0f, 0.0f};
PiezoSample lastPiezo = {0.0f, 0.0f};
bool vibrationValid = false;
float lastWaterTempC = NAN;

void handleRigCommand(bool pump1, bool pump2, int servoDeg) {
    const unsigned long now = millis();
    lastCommandTime = now;

    if (pump1 && !pump1Relay.getState()) pump1StartedAt = now;
    if (pump2 && !pump2Relay.getState()) pump2StartedAt = now;
    pump1 ? pump1Relay.on() : pump1Relay.off();
    pump2 ? pump2Relay.on() : pump2Relay.off();
    branchServo.setAngle(servoDeg);

    Serial.printf("[CMD] P1=%d P2=%d servo=%d\n", pump1, pump2, branchServo.getAngle());
}

void setup() {
    Serial.begin(115200);
    Serial.println("[ESP32] Initializing Water Leak Detection Rig...");

    flowIn.begin();
    flowOut.begin();
    flowBranch.begin();
    powerMeter.begin();  // initializes the shared Wire/I2C bus (SDA 21/SCL 22)
    vibrationSensor.begin();
    piezoSensor.begin();
    tempSensor.begin();
    pump1Relay.begin();
    pump2Relay.begin();
    branchServo.begin();

    calibrationPreferences.begin("flow-cal", false);
    flowIn.setKFactor(calibrationPreferences.getFloat("k1", K_FACTOR_FLOW_IN));
    flowOut.setKFactor(calibrationPreferences.getFloat("k2", K_FACTOR_FLOW_OUT));
    flowBranch.setKFactor(calibrationPreferences.getFloat("k3", K_FACTOR_FLOW_BRANCH));

    // Active-low relays must stay OFF until a complete supervised command.
    pump1Relay.off();
    pump2Relay.off();

    mqtt.connectWiFi(WIFI_SSID, WIFI_PASS);
    mqtt.connectMQTT(MQTT_BROKER, MQTT_PORT, DEVICE_ID);
    mqtt.setCommandCallback(handleRigCommand);

    Serial.println("[ESP32] Sensor node initialized. Awaiting supervised rig command.");
}

void loop() {
    mqtt.loop();

    const unsigned long now = millis();
    const bool commandTimedOut = now - lastCommandTime > COMMAND_WATCHDOG_MS;
    const bool pump1RuntimeExceeded = pump1Relay.getState() && now - pump1StartedAt > MAX_CONTINUOUS_PUMP_RUNTIME_MS;
    const bool pump2RuntimeExceeded = pump2Relay.getState() && now - pump2StartedAt > MAX_CONTINUOUS_PUMP_RUNTIME_MS;
    if ((commandTimedOut && (pump1Relay.getState() || pump2Relay.getState())) ||
        pump1RuntimeExceeded || pump2RuntimeExceeded) {
        pump1Relay.off();
        pump2Relay.off();
        Serial.println("[SAFETY] Pumps OFF: watchdog/runtime interlock");
    }

    // Acoustic burst + temperature read — both blocking (~1s and ~750ms
    // respectively), so these run on their own slower cadence rather than
    // every 1Hz telemetry tick (spec 5.3: bandwidth reduction, not detection
    // logic — thresholds stay in Python). The results are cached and
    // republished with every telemetry frame until the next burst.
    if (now - lastVibrationBurstTime >= VIBRATION_BURST_INTERVAL_MS) {
        lastVibrationBurstTime = now;
        if (vibrationSensor.isReady()) {
            lastVibration = vibrationSensor.sampleBurst();
            lastPiezo = piezoSensor.sampleBurst();
            vibrationValid = lastVibration.valid;
        }
        if (tempSensor.isReady()) {
            lastWaterTempC = tempSensor.readWaterC();
        }
    }

    if (now - lastTelemetryTime >= 1000) {
        lastTelemetryTime = now;

        const float qIn = flowIn.readFlowLPM();
        const float qOut = flowOut.readFlowLPM();
        const float qBranch = flowBranch.readFlowLPM();
        const float currentMA = powerMeter.readCurrentMA();
        const float voltageV = powerMeter.readVoltageV();

        const time_t epoch = time(nullptr);
        const unsigned long ts = (epoch > 1700000000) ? (unsigned long)epoch : (now / 1000);

        mqtt.publishTelemetry(
            ts, telemetrySequence++, qIn, qOut, qBranch, currentMA, voltageV,
            flowIn.getWindowPulses(), flowOut.getWindowPulses(), flowBranch.getWindowPulses(),
            pump1Relay.getState(), pump2Relay.getState(), branchServo.getAngle(),
            now / 1000, WiFi.RSSI(), ESP.getFreeHeap(),
            lastVibration, lastPiezo, vibrationValid, lastWaterTempC
        );
    }

    if (now - lastStatusTime >= 10000) {
        lastStatusTime = now;
        mqtt.publishStatus(WiFi.RSSI(), now / 1000, ESP.getFreeHeap());
    }
}
