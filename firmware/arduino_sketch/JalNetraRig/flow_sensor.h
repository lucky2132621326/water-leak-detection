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
#ifndef FLOW_SENSOR_H
#define FLOW_SENSOR_H

#include <Arduino.h>

class FlowSensor {
private:
    uint8_t pin;
    float kFactor;
    volatile uint32_t pulseCount;
    uint32_t lastPulseCount;
    uint32_t lastWindowPulses;
    unsigned long lastReadMs;

    static void IRAM_ATTR isrHandler(void* arg);

public:
    FlowSensor(uint8_t gpioPin, float kFactorValue);
    void begin();
    void handleISR();
    float readFlowLPM();
    uint32_t getTotalPulses();
    // Pulses counted during the most recent readFlowLPM() window — the same
    // delta the L/min figure was derived from. This is what MQTT telemetry's
    // "pulses_in/out/branch" fields must report (spec §5.3): raw counts that
    // let every historical L/min figure be recomputed if a K-factor turns out
    // wrong later. getTotalPulses() is cumulative since boot and is NOT that.
    uint32_t getWindowPulses() const { return lastWindowPulses; }
    void setKFactor(float pulsesPerLitre);
};

#endif
