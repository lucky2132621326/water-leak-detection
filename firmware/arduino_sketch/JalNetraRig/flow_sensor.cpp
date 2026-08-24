// -----------------------------------------------------------------------------
// NOT COMPILED INTO THE RUNNING FIRMWARE.
//
// main.cpp implements this functionality inline and does not include this
// header. PlatformIO still compiles everything in src/, so this file builds and
// occupies flash, but nothing calls it — editing it will NOT change rig
// behaviour. Left in place deliberately rather than deleted: removing files is
// a build risk that buys nothing.
//
// Change the pulse ISRs and toLpm() in main.cpp instead.
// -----------------------------------------------------------------------------
#include "flow_sensor.h"

FlowSensor::FlowSensor(uint8_t gpioPin, float kFactorValue)
    : pin(gpioPin), kFactor(kFactorValue), pulseCount(0), lastPulseCount(0), lastWindowPulses(0), lastReadMs(0) {}

void IRAM_ATTR FlowSensor::isrHandler(void* arg) {
    FlowSensor* self = static_cast<FlowSensor*>(arg);
    self->pulseCount++;
}

void FlowSensor::begin() {
    // External 10k/20k divider conditions the 5V open-collector signal.
    pinMode(pin, INPUT);
    lastReadMs = millis();
    // attachInterruptArg lets each instance register its own ISR without a
    // global lookup table — required since FlowSensor::handleISR can't be
    // used directly as a C function pointer.
    attachInterruptArg(digitalPinToInterrupt(pin), isrHandler, this, RISING);
}

void FlowSensor::handleISR() {
    pulseCount++;
}

float FlowSensor::readFlowLPM() {
    unsigned long now = millis();
    unsigned long elapsedMs = now - lastReadMs;
    if (elapsedMs == 0) return 0.0f;

    noInterrupts();
    uint32_t currentPulses = pulseCount;
    interrupts();

    uint32_t deltaPulses = currentPulses - lastPulseCount;
    lastPulseCount = currentPulses;
    lastWindowPulses = deltaPulses;
    lastReadMs = now;

    float pulsesPerSec = (float)deltaPulses / ((float)elapsedMs / 1000.0f);
    float lpm = pulsesPerSec / kFactor * 60.0f;
    return (lpm < 0.05f) ? 0.0f : lpm;
}

uint32_t FlowSensor::getTotalPulses() {
    noInterrupts();
    uint32_t total = pulseCount;
    interrupts();
    return total;
}

void FlowSensor::setKFactor(float pulsesPerLitre) {
    if (pulsesPerLitre > 0.0f) kFactor = pulsesPerLitre;
}
