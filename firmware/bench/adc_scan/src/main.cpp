#include <Arduino.h>

static constexpr int RELAY_1 = 25;
static constexpr int RELAY_2 = 26;
static constexpr int ADC_PINS[] = {33, 36, 39};

void setup() {
    pinMode(RELAY_1, OUTPUT);
    pinMode(RELAY_2, OUTPUT);
    digitalWrite(RELAY_1, HIGH);  // active-low relay: pump OFF
    digitalWrite(RELAY_2, HIGH);

    Serial.begin(115200);
    analogReadResolution(12);
    for (int pin : ADC_PINS) {
        pinMode(pin, INPUT);
        analogSetPinAttenuation(pin, ADC_11db);
    }
    delay(500);
    Serial.println("[ADC-SCAN] Pump relays forced OFF. Scanning GPIO33/36/39.");
}

void loop() {
    for (int pin : ADC_PINS) {
        uint32_t sumMV = 0;
        uint16_t minMV = UINT16_MAX;
        uint16_t maxMV = 0;
        for (int i = 0; i < 256; ++i) {
            uint16_t mv = analogReadMilliVolts(pin);
            sumMV += mv;
            minMV = min(minMV, mv);
            maxMV = max(maxMV, mv);
            delayMicroseconds(250);
        }
        Serial.printf("GPIO%d avg=%lumV min=%umV max=%umV spread=%umV | ",
                      pin, sumMV / 256, minMV, maxMV, maxMV - minMV);
    }
    Serial.println();
    delay(1000);
}
