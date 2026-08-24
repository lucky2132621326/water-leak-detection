#include "mqtt_client.h"
#include "config.h"

#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <time.h>

static WiFiClient wifiClient;
static PubSubClient client(wifiClient);
static CommandHandler commandHandler = nullptr;

static void handleMessage(char* topic, byte* payload, unsigned int length) {
    if (!commandHandler) return;

    StaticJsonDocument<256> doc;
    if (deserializeJson(doc, payload, length)) {
        Serial.println("[MQTT] malformed command payload — ignored");
        return;
    }

    const bool hasPump1 = doc.containsKey("pump1");
    const bool hasPump2 = doc.containsKey("pump2");
    const bool hasServo = doc.containsKey("servo_deg");
    if (!hasPump1 && !hasPump2 && !hasServo) {
        Serial.println("[MQTT] command contains no supported fields — ignored");
        return;
    }

    // containsKey, not a defaulted read. A command that mentions only the servo
    // must not be interpreted as "and also stop both pumps".
    commandHandler(
        hasPump1, doc["pump1"] | false,
        hasPump2, doc["pump2"] | false,
        hasServo, doc["servo_deg"] | 0);
}

void MQTTHandler::begin(CommandHandler handler) {
    commandHandler = handler;
    onCommand = handler;
    connectWiFi();
    client.setServer(MQTT_HOST, MQTT_PORT);
    client.setCallback(handleMessage);
    // Telemetry with the vibration block runs past the 256-byte default.
    client.setBufferSize(1024);
    reconnect();
}

void MQTTHandler::connectWiFi() {
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    Serial.print("[WiFi] connecting");

    // Bounded. An unbounded wait would block the loop forever with the pumps in
    // whatever state they were left — the relays are already OFF from setup(),
    // and that must stay true even if the network never comes up.
    for (int i = 0; i < 40 && WiFi.status() != WL_CONNECTED; i++) {
        delay(500);
        Serial.print(".");
    }
    Serial.println();

    if (WiFi.status() != WL_CONNECTED) {
        Serial.println("[WiFi] not connected — running offline, pumps stay off");
        return;
    }
    Serial.printf("[WiFi] connected, IP %s\n", WiFi.localIP().toString().c_str());

    // Sync wall-clock time so telemetry `ts` is a real Unix epoch. Until this
    // completes, publishTelemetry sends ts=0 rather than uptime.
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
}

void MQTTHandler::reconnect() {
    if (WiFi.status() != WL_CONNECTED) return;
    for (int attempt = 0; attempt < 3 && !client.connected(); attempt++) {
        // Last Will: if this node drops off without saying goodbye, the broker
        // publishes "offline" on the retained status topic. Without it the
        // dashboard cannot distinguish a dead rig from an idle one.
        char lastWill[128];
        snprintf(lastWill, sizeof(lastWill),
                 "{\"device\":\"%s\",\"status\":\"OFFLINE\"}", DEVICE_ID);
        bool connected = false;
        if (strlen(MQTT_USERNAME) > 0) {
            connected = client.connect(
                DEVICE_ID, MQTT_USERNAME, MQTT_PASSWORD,
                TOPIC_STATUS, 1, true, lastWill);
        } else {
            connected = client.connect(
                DEVICE_ID, TOPIC_STATUS, 1, true, lastWill);
        }
        if (connected) {
            client.subscribe(TOPIC_CMD, 1);
            publishStatus("online");
            Serial.println("[MQTT] connected");
            return;
        }
        delay(1000);
    }
}

void MQTTHandler::loop() {
    if (!client.connected()) reconnect();
    client.loop();
}

bool MQTTHandler::isConnected() {
    return client.connected();
}

void MQTTHandler::publishStatus(const char* state) {
    if (!client.connected()) return;
    StaticJsonDocument<192> doc;
    doc["device"] = DEVICE_ID;
    doc["status"] = state;
    doc["wifi_rssi"] = WiFi.RSSI();
    doc["uptime_sec"] = millis() / 1000;
    doc["heap_free"] = ESP.getFreeHeap();
    char buffer[192];
    const size_t n = serializeJson(doc, buffer);
    client.publish(
        TOPIC_STATUS,
        reinterpret_cast<const uint8_t*>(buffer),
        n,
        true);
}

void MQTTHandler::publishTelemetry(uint32_t seq, double ts, bool clockSynced,
                                   float qIn, float qOut, float qBranch,
                                   uint32_t pulsesIn, uint32_t pulsesOut, uint32_t pulsesBranch,
                                   float busV, float currentMA, float powerMW,
                                   const VibrationSample& vib,
                                   float waterC, bool tempPresent,
                                   bool pump1, bool pump2, int servoDeg, bool acs712Present,
                                   uint32_t uptimeSec) {
    if (!client.connected()) return;

    StaticJsonDocument<1024> doc;
    doc["ts"] = ts;
    doc["seq"] = seq;
    doc["device"] = DEVICE_ID;
    doc["fw_version"] = FW_VERSION;
    doc["schema_version"] = SCHEMA_VERSION;
    doc["mode"] = "live";
    // Explicit, so the backend never has to infer whether the clock is real.
    doc["clock_synced"] = clockSynced;

    JsonObject flow = doc.createNestedObject("flow");
    flow["q_in_lpm"]     = qIn;
    flow["q_out_lpm"]    = qOut;
    flow["q_branch_lpm"] = qBranch;
    // Raw counts alongside the converted rates, always. If a K-factor is later
    // recalibrated, every stored experiment can be recomputed from these instead
    // of re-running physical tests that may not be reproducible.
    flow["pulses_in"]     = pulsesIn;
    flow["pulses_out"]    = pulsesOut;
    flow["pulses_branch"] = pulsesBranch;

    JsonObject power = doc.createNestedObject("power");
    if (!isnan(busV))      power["bus_v"] = busV;
    else                   power["bus_v"] = (char*)nullptr;
    if (!isnan(currentMA)) power["current_ma"] = currentMA;
    else                   power["current_ma"] = (char*)nullptr;
    if (!isnan(powerMW))   power["power_mw"] = powerMW;
    else                   power["power_mw"] = (char*)nullptr;
    power["current_source"] = acs712Present ? "acs712" : (!isnan(currentMA) ? "ina219" : "unavailable");

    JsonObject v = doc.createNestedObject("vibration");
    if (vib.hasAccelerometer) {
        v["rms"]       = vib.rms;
        v["band_low"]  = vib.bandLow;
        v["band_mid"]  = vib.bandMid;
        v["band_high"] = vib.bandHigh;
    } else {
        // null, not 0.0. Zero is a reading from a quiet pipe; null is no sensor.
        // The backend marks the acoustic channel inactive and renormalises the
        // fusion weights rather than scoring the rig as if it had been listened to.
        v["rms"] = v["band_low"] = v["band_mid"] = v["band_high"] = (char*)nullptr;
    }
    if (vib.hasPiezo) {
        v["piezo_rms"]         = vib.piezoRms;
        v["piezo_centroid_hz"] = vib.piezoCentroid;
    } else {
        // The piezo disc is optional hardware — same reasoning as above.
        v["piezo_rms"] = v["piezo_centroid_hz"] = (char*)nullptr;
    }

    JsonObject temp = doc.createNestedObject("temp");
    if (tempPresent && !isnan(waterC)) temp["water_c"] = waterC;
    else                               temp["water_c"] = (char*)nullptr;

    JsonObject act = doc.createNestedObject("actuators");
    act["pump1"]     = pump1;
    act["pump2"]     = pump2;
    act["servo_deg"] = servoDeg;
    // No solenoid_state. This rig has no solenoid: leaks are opened by hand on a
    // worm-drive clamp, and ground truth is recorded by the operator, not sensed.

    JsonObject health = doc.createNestedObject("health");
    health["uptime_s"]  = uptimeSec;
    health["wifi_rssi"] = WiFi.RSSI();
    health["free_heap"] = ESP.getFreeHeap();
    JsonObject sensors = health.createNestedObject("sensors");
    sensors["flow_1"] = true;
    sensors["flow_2"] = true;
    sensors["flow_3"] = true;
    sensors["mpu6050"] = vib.hasAccelerometer;
    sensors["ina219"] = !acs712Present && !isnan(currentMA);
    sensors["acs712"] = acs712Present;

    char buffer[1024];
    const size_t n = serializeJson(doc, buffer);
    client.publish(
        TOPIC_TELEMETRY,
        reinterpret_cast<const uint8_t*>(buffer),
        n,
        false);
}
