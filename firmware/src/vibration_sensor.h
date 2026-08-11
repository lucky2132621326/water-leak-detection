#ifndef VIBRATION_SENSOR_H
#define VIBRATION_SENSOR_H

#include <Arduino.h>
#include <Adafruit_MPU6050.h>

struct VibrationSample {
    bool valid;
    float rms;
    float band_low;   // 10-50 Hz
    float band_mid;   // 50-150 Hz — leak jet energy concentrates here
    float band_high;  // 150-250 Hz
};

// Bandwidth reduction, not detection logic (hardware spec v2 section 5.3):
// thresholds/ratios stay entirely in the Python backend. This class only
// turns a burst of raw accelerometer samples into three band-energy
// summaries via FFT, since streaming raw samples at 1 Hz isn't feasible.
class VibrationSensor {
private:
    Adafruit_MPU6050 mpu;
    bool ready;

public:
    VibrationSensor();
    void begin();
    bool isReady() const { return ready; }
    // Blocking for ~VIBRATION_SAMPLE_COUNT/VIBRATION_SAMPLE_RATE_HZ seconds
    // (~1s at the spec defaults) — call on a slower cadence than the 1Hz
    // telemetry loop, not every iteration.
    VibrationSample sampleBurst();
};

#endif
