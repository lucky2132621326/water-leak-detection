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
