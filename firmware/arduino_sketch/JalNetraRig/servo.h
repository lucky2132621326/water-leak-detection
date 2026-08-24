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
#ifndef SERVO_H
#define SERVO_H

#include <Arduino.h>
#include <ESP32Servo.h>

class ServoController {
private:
    uint8_t pin;
    Servo servo;
    int currentAngle;

public:
    ServoController(uint8_t gpioPin);
    void begin();
    void setAngle(int angleDegrees);
    int getAngle();
};

#endif
