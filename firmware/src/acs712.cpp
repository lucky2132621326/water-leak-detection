#include "acs712.h"

#include <math.h>

#include "config.h"

float ACS712Sensor::readAveragedAdcMV(size_t samples) const {
    double sum = 0.0;
    for (size_t i = 0; i < samples; ++i) {
        // Arduino-ESP32 applies the board's ADC calibration and returns the
        // voltage at the ESP32 pin. The divider is reversed below to recover
        // the voltage at ACS712 OUT.
        sum += analogReadMilliVolts(PIN_ACS712);
        delayMicroseconds(250);
    }
    return samples ? static_cast<float>(sum / samples) : NAN;
}

bool ACS712Sensor::begin() {
#if !ENABLE_ACS712
    ready = false;
    return false;
#else
    pinMode(PIN_ACS712, INPUT);
    analogReadResolution(12);
    analogSetPinAttenuation(PIN_ACS712, ADC_11db);

    delay(100);
    const float adcZeroMV = readAveragedAdcMV(ACS712_ZERO_SAMPLES);
    zeroSensorMV = adcZeroMV / ACS712_ADC_DIVIDER_RATIO;

    // A healthy 5 V ACS712 rests near 2.5 V. A broad validity window allows
    // resistor/ADC tolerance while still rejecting ground or rail instead of
    // publishing plausible-looking fake current.
    ready = isfinite(zeroSensorMV) && zeroSensorMV >= 1800.0f && zeroSensorMV <= 3200.0f;
    return ready;
#endif
}

float ACS712Sensor::readCurrentMA() {
    if (!ready) return NAN;

    const float adcMV = readAveragedAdcMV(ACS712_READ_SAMPLES);
    const float sensorMV = adcMV / ACS712_ADC_DIVIDER_RATIO;
    float currentMA = fabsf(sensorMV - zeroSensorMV)
                      * (1000.0f / ACS712_SENSITIVITY_MV_PER_A);
    if (currentMA < ACS712_NOISE_FLOOR_MA) currentMA = 0.0f;
    return currentMA;
}
