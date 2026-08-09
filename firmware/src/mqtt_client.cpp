#include "mqtt_client.h"
#include "config.h"
#include <ArduinoJson.h>
#include <time.h>

// Static instance pointer so the C-style PubSubClient callback can reach
// the owning MQTTHandler (PubSubClient doesn't support member-function
// callbacks or a user-data argument).
static MQTTHandler* g_instance = nullptr;

static void staticMessageCallback(char* topic, byte* payload, unsigned int length) {
    if (g_instance) g_instance->handleMessage(topic, payload, length);
}

MQTTHandler::MQTTHandler() : client(wifiClient), deviceId(DEVICE_ID), lastReconnectAttempt(0), onCommand(nullptr) {
    g_instance = this;
}

void MQTTHandler::connectWiFi(const char* ssid, const char* password) {
    Serial.printf("[WiFi] Connecting to %s...\n", ssid);
    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED && (millis() - start) < 20000) {
        delay(250);
        Serial.print(".");
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WiFi] Connected, IP: %s\n", WiFi.localIP().toString().c_str());
        // Sync wall-clock time via NTP so telemetry "ts" is a real Unix timestamp.
        configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    } else {
        Serial.println("\n[WiFi] FAILED to connect within timeout — will keep retrying in loop()");
    }
}

void MQTTHandler::connectMQTT(const char* broker, int port, const char* clientID) {
    client.setServer(broker, port);
    client.setCallback(staticMessageCallback);
    client.setBufferSize(768);
    deviceId = clientID;
    reconnect();
}

void MQTTHandler::reconnect() {
    if (WiFi.status() != WL_CONNECTED) return;
    if (client.connected()) return;

    Serial.printf("[MQTT] Connecting to broker as %s...\n", deviceId);
    char lastWill[128];
    snprintf(lastWill, sizeof(lastWill), "{\"device\":\"%s\",\"status\":\"OFFLINE\"}", deviceId);
    if (client.connect(deviceId, MQTT_TOPIC_STATUS, 1, true, lastWill)) {
        Serial.println("[MQTT] Connected");
        client.subscribe(MQTT_TOPIC_CMD);
        char online[128];
        snprintf(online, sizeof(online), "{\"device\":\"%s\",\"status\":\"ONLINE\"}", deviceId);
        client.publish(MQTT_TOPIC_STATUS, online, true);
    } else {
        Serial.printf("[MQTT] Connect failed, rc=%d\n", client.state());
    }
}

void MQTTHandler::setCommandCallback(CommandCallback cb) {
    onCommand = cb;
}

void MQTTHandler::handleMessage(char* topic, byte* payload, unsigned int length) {
    StaticJsonDocument<256> doc;
    DeserializationError err = deserializeJson(doc, payload, length);
    if (err) {
        Serial.printf("[MQTT] Bad command payload: %s\n", err.c_str());
        return;
    }

    if (onCommand && doc.containsKey("pump1") && doc.containsKey("pump2") && doc.containsKey("servo_deg")) {
        onCommand(doc["pump1"].as<bool>(), doc["pump2"].as<bool>(), doc["servo_deg"].as<int>());
    } else {
        Serial.println("[MQTT] Rejected incomplete rig command");
    }
}

void MQTTHandler::loop() {
    if (WiFi.status() != WL_CONNECTED) return;
    if (!client.connected()) {
        unsigned long now = millis();
        if (now - lastReconnectAttempt > 5000) {
            lastReconnectAttempt = now;
            reconnect();
        }
        return;
    }
    client.loop();
}

bool MQTTHandler::isConnected() {
    return client.connected();
}

void MQTTHandler::publishTelemetry(unsigned long ts, uint32_t seq, float qIn, float qOut, float qBranch,
                                    float currentMA, float voltageV,
                                    uint32_t rawPulsesIn, uint32_t rawPulsesOut, uint32_t rawPulsesBranch,
                                    bool pump1On, bool pump2On, int servoDeg,
                                    unsigned long uptimeSec, int wifiRssi, uint32_t freeHeap) {
    StaticJsonDocument<768> doc;
    doc["ts"] = ts;
    doc["seq"] = seq;
    doc["device"] = deviceId;

    JsonObject flow = doc.createNestedObject("flow");
    flow["q_in_lpm"] = qIn;
    flow["q_out_lpm"] = qOut;
    flow["q_branch_lpm"] = qBranch;
    flow["pulses_in"] = rawPulsesIn;
    flow["pulses_out"] = rawPulsesOut;
    flow["pulses_branch"] = rawPulsesBranch;

    JsonObject power = doc.createNestedObject("power");
    power["bus_v"] = voltageV;
    power["current_ma"] = currentMA;
    power["power_mw"] = voltageV * currentMA;

    JsonObject actuators = doc.createNestedObject("actuators");
    actuators["pump1"] = pump1On;
    actuators["pump2"] = pump2On;
    actuators["servo_deg"] = servoDeg;

    JsonObject health = doc.createNestedObject("health");
    health["uptime_s"] = uptimeSec;
    health["wifi_rssi"] = wifiRssi;
    health["free_heap"] = freeHeap;
    // pressure_bar intentionally omitted — no physical pressure sensor on this
    // rig; the backend derives an estimated value (see docs/MQTT_SPEC.md note).
    char buf[768];
    size_t n = serializeJson(doc, buf);

    if (client.connected()) {
        client.publish(MQTT_TOPIC_TELEMETRY, buf, n);
    } else {
        Serial.printf("[Telemetry] (offline) Qin: %.2f | Qout: %.2f | Qbr: %.2f | I: %.1fmA\n", qIn, qOut, qBranch, currentMA);
    }
}

void MQTTHandler::publishStatus(int wifiRssi, unsigned long uptimeSec, uint32_t heapFree) {
    StaticJsonDocument<192> doc;
    doc["device"] = deviceId;
    doc["wifi_rssi"] = wifiRssi;
    doc["uptime_sec"] = uptimeSec;
    doc["heap_free"] = heapFree;
    doc["status"] = client.connected() ? "ONLINE" : "DEGRADED";

    char buf[192];
    size_t n = serializeJson(doc, buf);
    if (client.connected()) {
        client.publish(MQTT_TOPIC_STATUS, buf, n, true);
    }
}
