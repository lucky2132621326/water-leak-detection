#ifndef MQTT_CLIENT_H
#define MQTT_CLIENT_H

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include "vibration_sensor.h"
#include "piezo_sensor.h"

// Forward-declared so main.cpp can wire valve/pump commands received on
// rig/cmd back into the RelayController/ServoController instances without
// this class needing to know about them directly.
typedef void (*CommandCallback)(bool pump1, bool pump2, int servoDeg);

class MQTTHandler {
private:
    WiFiClient wifiClient;
    PubSubClient client;
    const char* deviceId;
    unsigned long lastReconnectAttempt;
    CommandCallback onCommand;

    void reconnect();

public:
    MQTTHandler();
    void connectWiFi(const char* ssid, const char* password);
    void connectMQTT(const char* broker, int port, const char* clientID);
    void setCommandCallback(CommandCallback cb);
    // Public so the free-function PubSubClient callback can reach it —
    // PubSubClient only supports a plain function pointer, not a member fn.
    void handleMessage(char* topic, byte* payload, unsigned int length);
    void loop();
    bool isConnected();
    void publishTelemetry(unsigned long ts, uint32_t seq, float qIn, float qOut, float qBranch,
                           float currentMA, float voltageV,
                           uint32_t rawPulsesIn, uint32_t rawPulsesOut, uint32_t rawPulsesBranch,
                           bool pump1On, bool pump2On, int servoDeg,
                           unsigned long uptimeSec, int wifiRssi, uint32_t freeHeap,
                           const VibrationSample& vibration, const PiezoSample& piezo, bool vibrationValid,
                           float waterTempC);
    void publishStatus(int wifiRssi, unsigned long uptimeSec, uint32_t heapFree);
};

#endif
