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
#include "temp_sensor.h"

TempSensor::TempSensor(uint8_t pin) : oneWire(pin), sensors(&oneWire), ready(false) {}

void TempSensor::begin() {
    sensors.begin();
    ready = sensors.getDeviceCount() > 0;
    if (!ready) {
        Serial.println("[DS18B20] WARNING: no sensor found on 1-Wire bus (check the 4.7k pull-up) — temp compensation inert");
    }
}

float TempSensor::readWaterC() {
    if (!ready) return NAN;
    sensors.requestTemperatures();
    float c = sensors.getTempCByIndex(0);
    return (c == DEVICE_DISCONNECTED_C) ? NAN : c;
}
