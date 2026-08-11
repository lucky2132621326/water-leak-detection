/*
 * First hardware milestone (spec section 5.7): verify a single flow sensor's
 * pulse train is being counted correctly before wiring anything else.
 * No WiFi, no MQTT, no I2C — just GPIO34 -> serial pulse count, once a second.
 *
 * Flash with PlatformIO from this directory (platformio.ini alongside this
 * file), or open in Arduino IDE — the folder name must match the .ino name,
 * which it already does here.
 */
#include <Arduino.h>

#define PIN_FLOW_IN 34  // input-only pin; do NOT enable INPUT_PULLUP — the
                        // sensor's open-collector output already has an
                        // external 10k/20k divider to bring 5V down to 3V3.

volatile uint32_t pulse_in = 0;
portMUX_TYPE pulseMux = portMUX_INITIALIZER_UNLOCKED;

void IRAM_ATTR isr_in() {
  pulse_in++;
}

unsigned long lastPrintMs = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_FLOW_IN, INPUT);
  attachInterrupt(digitalPinToInterrupt(PIN_FLOW_IN), isr_in, RISING);
  Serial.println("[serial_test] Watching GPIO34 pulses, 1 print/sec...");
  lastPrintMs = millis();
}

void loop() {
  unsigned long now = millis();
  if (now - lastPrintMs >= 1000) {
    lastPrintMs = now;

    portENTER_CRITICAL(&pulseMux);
    uint32_t count = pulse_in;
    pulse_in = 0;
    portEXIT_CRITICAL(&pulseMux);

    Serial.printf("pulses/sec: %u\n", count);
  }
}
