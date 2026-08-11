// -----------------------------------------------------------------------------
// NOT COMPILED INTO THE RUNNING FIRMWARE.
//
// main.cpp implements this functionality inline and does not include this
// header. PlatformIO still compiles everything in src/, so this file builds and
// occupies flash, but nothing calls it — editing it will NOT change rig
// behaviour. Left in place deliberately rather than deleted: removing files is
// a build risk that buys nothing.
//
// Change the DallasTemperature calls in main.cpp instead.
// -----------------------------------------------------------------------------
#ifndef TEMP_SENSOR_H
#define TEMP_SENSOR_H

#include <Arduino.h>
#include <OneWire.h>
#include <DallasTemperature.h>

// DS18B20 submerged in the reservoir. Conversion takes ~750ms at default
// 12-bit resolution, which is why this is sampled on the same slow cadence
// as the vibration burst rather than every 1Hz telemetry tick.
class TempSensor {
private:
    OneWire oneWire;
    DallasTemperature sensors;
    bool ready;

public:
    explicit TempSensor(uint8_t pin);
    void begin();
    bool isReady() const { return ready; }
    // NAN if no sensor was found — callers must check isReady() first or
    // handle NAN explicitly; never silently substitute a plausible value.
    float readWaterC();
};

#endif
