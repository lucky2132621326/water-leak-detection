#ifndef MQTT_CLIENT_H
#define MQTT_CLIENT_H

#include <Arduino.h>
#include "vibration_sensor.h"

// MQTT transport for the sensor node.
//
// Publishes the nested telemetry contract in docs/MQTT_SPEC.md (spec Part G) on
// `rig/telemetry`, subscribes to `rig/cmd`, and keeps a retained `rig/status`
// with a Last Will so the dashboard can tell "offline" from "quiet".

// hasPump1/hasPump2/hasServo distinguish "absent from the payload" from
// "present and false". A command that only mentions the servo must not be read
// as an instruction to stop both pumps.
typedef void (*CommandHandler)(bool hasPump1, bool pump1,
                               bool hasPump2, bool pump2,
                               bool hasServo, int servoDeg);

class MQTTHandler {
public:
    void begin(CommandHandler handler);
    void loop();

    // `clockSynced` false means NTP has not completed and `ts` is not
    // meaningful. The field is published as 0 in that case rather than filled
    // with uptime, which would put a different epoch in the same field and be
    // undetectable downstream.
    void publishTelemetry(double ts, bool clockSynced,
                          float qIn, float qOut, float qBranch,
                          uint32_t pulsesIn, uint32_t pulsesOut, uint32_t pulsesBranch,
                          float busV, float currentMA, float powerMW,
                          const VibrationSample& vib,
                          float waterC, bool tempPresent,
                          bool pump1, bool pump2, int servoDeg,
                          uint32_t uptimeSec);

    void publishStatus(const char* state);
    bool isConnected();

private:
    CommandHandler onCommand = nullptr;
    void connectWiFi();
    void reconnect();
};

#endif  // MQTT_CLIENT_H
