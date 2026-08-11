// -----------------------------------------------------------------------------
// NOT COMPILED INTO THE RUNNING FIRMWARE.
//
// main.cpp implements this functionality inline and does not include this
// header. PlatformIO still compiles everything in src/, so this file builds and
// occupies flash, but nothing calls it — editing it will NOT change rig
// behaviour. Left in place deliberately rather than deleted: removing files is
// a build risk that buys nothing.
//
// Change the servo branch of onCommand() in main.cpp instead.
// -----------------------------------------------------------------------------
#include "servo.h"

ServoController::ServoController(uint8_t gpioPin) : pin(gpioPin), currentAngle(0) {}

void ServoController::begin() {
    servo.setPeriodHertz(50);
    servo.attach(pin, 500, 2400);
    setAngle(0);
}

void ServoController::setAngle(int angleDegrees) {
    currentAngle = constrain(angleDegrees, 0, 180);
    servo.write(currentAngle);
}

int ServoController::getAngle() {
    return currentAngle;
}
