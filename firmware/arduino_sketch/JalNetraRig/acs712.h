#ifndef ACS712_SENSOR_H
#define ACS712_SENSOR_H

#include <Arduino.h>

// DC-current reader for the analogue ACS712 module. The zero point is learned
// at boot while both pump relays are already OFF, avoiding a hard-coded 2.5 V
// midpoint that would be distorted by ADC and resistor tolerances.
class ACS712Sensor {
public:
    bool begin();
    float readCurrentMA();
    float zeroPointMV() const { return zeroSensorMV; }

private:
    float readAveragedAdcMV(size_t samples) const;
    float zeroSensorMV = NAN;
    bool ready = false;
};

#endif  // ACS712_SENSOR_H
