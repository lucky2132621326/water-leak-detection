// -----------------------------------------------------------------------------
// NOT COMPILED INTO THE RUNNING FIRMWARE.
//
// main.cpp implements this functionality inline and does not include this
// header. PlatformIO still compiles everything in src/, so this file builds and
// occupies flash, but nothing calls it — editing it will NOT change rig
// behaviour. Left in place deliberately rather than deleted: removing files is
// a build risk that buys nothing.
//
// Change VibrationSensor::readPiezo() in vibration_sensor.cpp instead.
// -----------------------------------------------------------------------------
#include "piezo_sensor.h"
#include "config.h"

static int16_t rawSamples[PIEZO_SAMPLE_COUNT];

void PiezoSensor::begin() {
    pinMode(PIN_PIEZO, INPUT);
    analogReadResolution(12);
}

PiezoSample PiezoSensor::sampleBurst() {
    const unsigned long periodUs = 1000000UL / PIEZO_SAMPLE_RATE_HZ;
    double mean = 0.0;

    for (int i = 0; i < PIEZO_SAMPLE_COUNT; i++) {
        unsigned long sampleStart = micros();
        rawSamples[i] = analogRead(PIN_PIEZO);
        mean += rawSamples[i];
        while (micros() - sampleStart < periodUs) {
            // Busy-wait to hold the 2 kHz sample rate.
        }
    }
    mean /= PIEZO_SAMPLE_COUNT;

    double sumSq = 0.0;
    int zeroCrossings = 0;
    int prevSign = 0;
    for (int i = 0; i < PIEZO_SAMPLE_COUNT; i++) {
        double centered = rawSamples[i] - mean;
        sumSq += centered * centered;
        int sign = (centered >= 0.0) ? 1 : -1;
        if (i > 0 && sign != prevSign) zeroCrossings++;
        prevSign = sign;
    }

    PiezoSample result;
    // Normalize by full-scale 12-bit range so this is a unitless ~0-1 figure
    // comparable across boards, not raw ADC counts.
    result.rms = (float)(sqrt(sumSq / PIEZO_SAMPLE_COUNT) / 4095.0);
    const float durationSec = (float)PIEZO_SAMPLE_COUNT / (float)PIEZO_SAMPLE_RATE_HZ;
    result.centroid_hz = (zeroCrossings / 2.0f) / durationSec;
    return result;
}
