#ifndef PIEZO_SENSOR_H
#define PIEZO_SENSOR_H

#include <Arduino.h>

struct PiezoSample {
    float rms;
    float centroid_hz;
};

// Secondary acoustic channel — a contact-mic piezo disc on ADC1 (GPIO33,
// safe to read with WiFi active). No FFT here: centroid_hz is estimated
// from the zero-crossing rate, a standard cheap proxy for dominant
// frequency on a narrowband signal like a piezo contact mic, avoiding a
// second on-device FFT pass on top of the MPU6050's.
class PiezoSensor {
public:
    void begin();
    // Blocking for PIEZO_SAMPLE_COUNT/PIEZO_SAMPLE_RATE_HZ seconds (~0.25s
    // at spec defaults) — call alongside the vibration burst, not every
    // 1Hz telemetry tick.
    PiezoSample sampleBurst();
};

#endif
