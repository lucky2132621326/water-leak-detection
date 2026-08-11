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
#include "relay.h"

RelayController::RelayController(uint8_t gpioPin) : pin(gpioPin), state(false) {}

void RelayController::begin() {
    pinMode(pin, OUTPUT);
    off();
}

void RelayController::on() {
    digitalWrite(pin, LOW); // Active low relay
    state = true;
}

void RelayController::off() {
    digitalWrite(pin, HIGH);
    state = false;
}

bool RelayController::getState() {
    return state;
}
