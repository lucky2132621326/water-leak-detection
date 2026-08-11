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
