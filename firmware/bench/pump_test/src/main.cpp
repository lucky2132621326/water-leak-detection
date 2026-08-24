// Jal Netra — controlled Pump 1 relay bring-up test.
//
// This sketch intentionally has no Wi-Fi, MQTT, INA219, vibration, servo, or
// flow dependencies. It performs one short test and then latches the relay OFF.
// The full firmware uses the same GPIO and active-low relay contract.

#include <Arduino.h>

constexpr uint8_t PUMP1_RELAY_PIN = 25;
constexpr uint8_t RELAY_ON = LOW;
constexpr uint8_t RELAY_OFF = HIGH;
constexpr uint32_t START_WARNING_MS = 5000;
constexpr uint32_t TEST_RUN_MS = 2000;

void forcePumpOff() {
  digitalWrite(PUMP1_RELAY_PIN, RELAY_OFF);
}

void setup() {
  // Establish the safe state before starting Serial or doing anything that can
  // block. Most relay boards energize LOW, so a floating pin is unacceptable.
  pinMode(PUMP1_RELAY_PIN, OUTPUT);
  forcePumpOff();

  Serial.begin(115200);
  delay(250);
  Serial.println();
  Serial.println("[PUMP TEST] Pump 1 relay is OFF (GPIO 25, active-low).");
  Serial.println("[PUMP TEST] Ensure the pump is submerged/primed and outlet is open.");

  for (int seconds = START_WARNING_MS / 1000; seconds > 0; --seconds) {
    Serial.printf("[PUMP TEST] Starting one 2-second pulse in %d...\n", seconds);
    delay(1000);
  }

  Serial.println("[PUMP TEST] Pump 1 ON");
  digitalWrite(PUMP1_RELAY_PIN, RELAY_ON);
  delay(TEST_RUN_MS);

  forcePumpOff();
  Serial.println("[PUMP TEST] Pump 1 OFF — test complete and latched safe.");
}

void loop() {
  // Continuously reassert OFF. Reset the ESP32 to perform another short test.
  forcePumpOff();
  delay(100);
}
