// -----------------------------------------------------------------------------
// NOT COMPILED INTO THE RUNNING FIRMWARE.
//
// main.cpp implements this functionality inline and does not include this
// header. PlatformIO still compiles everything in src/, so this file builds and
// occupies flash, but nothing calls it — editing it will NOT change rig
// behaviour. Left in place deliberately rather than deleted: removing files is
// a build risk that buys nothing.
//
// Change the Adafruit_INA219 calls in main.cpp instead.
// -----------------------------------------------------------------------------
#ifndef INA219_H
#define INA219_H

#include <Arduino.h>
#include <Adafruit_INA219.h>

class INA219Sensor {
private:
    Adafruit_INA219 ina219;
    bool ready;

public:
    INA219Sensor();
    void begin();
    float readCurrentMA();
    float readVoltageV();
    bool isReady();
};

#endif
