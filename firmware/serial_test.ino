// =============================================================================
// serial_test.ino — FIRST hardware verification milestone
//
// ONE flow sensor on GPIO 34. Pulse count printed once per second over serial.
// No WiFi, no MQTT, no I2C, no libraries beyond the core.
//
// This exists so that when nothing works, you can find out whether the problem
// is the sensor, the wiring, or everything else. If this sketch does not count
// pulses, no amount of debugging the backend will help.
//
// WIRING (spec Part D)
//   YF-S201 red    -> 5V   (from LM2596 #1)
//   YF-S201 black  -> GND  (the SINGLE common ground rail — see note below)
//   YF-S201 yellow -> 10k/20k divider -> GPIO 34
//
//                    5V signal ---[10k]---+---[20k]--- GND
//                                         |
//                                      GPIO 34   (~3.33V)
//
//   The ESP32 is NOT 5V tolerant. Connecting the yellow wire straight to the
//   pin will damage it. The divider is not optional.
//
//   GROUND: the adapter negatives, both LM2596 OUT-, and the ESP32 GND must all
//   be bonded to one rail. A floating ground produces phantom pulse counts that
//   are indistinguishable from a leak — this is the single most common cause of
//   a rig that "detects leaks" while sitting still.
//
// EXPECTED OUTPUT
//   Still water        0 pulses/s
//   Blowing through it a few dozen pulses/s
//   Pump running       roughly 7.5 * Q(L/min), so ~39 pulses/s at 5.2 L/min
//
// CALIBRATION
//   Run water through into a measuring cylinder, note total pulses and total
//   litres. K = pulses / litres. Nominal is ~450 but per-unit variation is
//   significant — put YOUR measured value into K1/K2/K3 in firmware/src/config.h.
//   Never assume 450.
// =============================================================================

const int PIN_FLOW = 34;   // input-only pin; see the divider note above

volatile uint32_t pulseCount = 0;
uint32_t totalPulses = 0;
uint32_t lastReport = 0;

void IRAM_ATTR onPulse() {
    pulseCount++;
}

void setup() {
    Serial.begin(115200);
    delay(500);

    // INPUT, never INPUT_PULLUP. The sensor is open-collector to 5V and the
    // divider sets the level; an internal pull-up would fight it and produce
    // phantom counts.
    pinMode(PIN_FLOW, INPUT);
    attachInterrupt(digitalPinToInterrupt(PIN_FLOW), onPulse, RISING);

    Serial.println();
    Serial.println("=== Jal Netra flow sensor test — GPIO 34 ===");
    Serial.println("Blow through the sensor or run the pump. Ctrl-C to stop.");
    Serial.println("elapsed_s  pulses/s  total  est_L/min");
    lastReport = millis();
}

void loop() {
    const uint32_t now = millis();
    if (now - lastReport < 1000) return;
    const uint32_t elapsed = now - lastReport;
    lastReport = now;

    // Read and clear atomically: a pulse landing between the two would be lost.
    noInterrupts();
    const uint32_t pulses = pulseCount;
    pulseCount = 0;
    interrupts();

    totalPulses += pulses;

    // Datasheet approximation f = 7.5 * Q, shown only as a sanity check. The
    // real conversion uses the K-factor you measure yourself.
    const float lpm = (pulses * 1000.0f / elapsed) / 7.5f;

    Serial.printf("%9lu  %8lu  %5lu  %8.2f\n",
                  now / 1000, pulses, totalPulses, lpm);
}
