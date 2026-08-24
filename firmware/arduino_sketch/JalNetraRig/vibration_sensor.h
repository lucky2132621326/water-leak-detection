#ifndef VIBRATION_SENSOR_H
#define VIBRATION_SENSOR_H

#include <Arduino.h>

// Acoustic front end: MPU6050 accelerometer plus an optional piezo contact mic.
//
// Water forced through a leak orifice jets rather than flows, exciting the pipe
// wall broadband. On a rig this size the leak energy concentrates around
// 50-150 Hz, which is why that band is reported separately.
//
// This class does ONE job: turn a burst of samples into a handful of numbers so
// they fit in a 1 Hz telemetry packet. It makes no decisions. Every threshold,
// baseline and verdict lives in the Python backend — the on-device FFT is the
// single exception to "no processing on the ESP32", and it is there for
// bandwidth, not intelligence.
//
// The piezo is OPTIONAL hardware. When no disc is fitted, `hasPiezo` is false
// and the piezo fields are published as null rather than 0.0 — a silent
// microphone and an absent one are different facts, and collapsing them would
// let missing hardware read as evidence of a quiet pipe.

struct VibrationSample {
    bool  hasAccelerometer = false;
    float rms       = 0.0f;
    float bandLow   = 0.0f;   // 10-50 Hz
    float bandMid   = 0.0f;   // 50-150 Hz — the leak band
    float bandHigh  = 0.0f;   // 150-250 Hz

    bool  hasPiezo  = false;
    float piezoRms      = 0.0f;
    float piezoCentroid = 0.0f;
};

class VibrationSensor {
public:
    // Returns false if the MPU6050 does not answer on I2C. Detection must still
    // run in that case: the backend marks the acoustic channel inactive and
    // fusion renormalises around it.
    bool begin();

    // Detects a piezo by checking whether the ADC pin shows any signal activity
    // at all. A floating pin reads as noise around a fixed level; a real disc
    // with its 1M bleed resistor sits near zero and moves with the pipe.
    bool detectPiezo();

    // Blocking burst of ~1 s. Called once per telemetry interval.
    VibrationSample read();

    bool isPresent() const { return present; }

private:
    bool present  = false;
    bool piezo    = false;

    void  readAccelBurst(float* buffer, size_t count);
    void  computeBands(const float* buffer, size_t count, VibrationSample& out);
    void  readPiezo(VibrationSample& out);
};

#endif  // VIBRATION_SENSOR_H
