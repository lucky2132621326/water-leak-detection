// -----------------------------------------------------------------------------
// NOT COMPILED INTO THE RUNNING FIRMWARE.
//
// main.cpp implements this functionality inline and does not include this
// header. PlatformIO still compiles everything in src/, so this file builds and
// occupies flash, but nothing calls it — editing it will NOT change rig
// behaviour. Left in place deliberately rather than deleted: removing files is
// a build risk that buys nothing.
//
// Change setPump()/stopPumps() in main.cpp instead.
// -----------------------------------------------------------------------------
#ifndef RELAY_H
#define RELAY_H

#include <Arduino.h>

class RelayController {
private:
    uint8_t pin;
    bool state;

public:
    RelayController(uint8_t gpioPin);
    void begin();
    void on();
    void off();
    bool getState();
};

#endif
