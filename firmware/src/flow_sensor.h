#ifndef FLOW_SENSOR_H
#define FLOW_SENSOR_H

#include <Arduino.h>

class FlowSensor {
private:
    uint8_t pin;
    float kFactor;
    volatile uint32_t pulseCount;
    uint32_t lastPulseCount;
    unsigned long lastReadMs;

    static void IRAM_ATTR isrHandler(void* arg);

public:
    FlowSensor(uint8_t gpioPin, float kFactorValue);
    void begin();
    void handleISR();
    float readFlowLPM();
    uint32_t getTotalPulses();
    void setKFactor(float pulsesPerLitre);
};

#endif
