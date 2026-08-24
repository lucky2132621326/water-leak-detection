# Firmware Pinout Reference

```text
                  +--------------------+
                  |    ESP32 DEVKIT    |
                  |                    |
 Flow 1 interrupt | GPIO 34    GPIO 21 | INA219 / MPU6050 SDA
 Flow 2 interrupt | GPIO 35    GPIO 22 | INA219 / MPU6050 SCL
 Flow 3 interrupt | GPIO 32    GPIO 25 | Relay 1 (supply pump)
 Branch servo PWM | GPIO 27    GPIO 26 | Relay 2 (demand pump)
 ACS712 OUT ADC1  | GPIO 33     GPIO 4 | DS18B20 1-Wire
                  +--------------------+
```

Flow-sensor outputs require the documented level shifting because the ESP32 is
not 5 V tolerant. GPIO 34 and 35 are input-only, and the firmware deliberately
does not enable internal pull-ups on any flow input.

The current rig has no pressure transducer and no leak solenoid. Pressure shown
by the dashboard is explicitly labelled as an estimate; physical leak windows
are opened manually and recorded as operator ground truth.

The ACS712 is powered from 5 V, but its `OUT` signal must reach GPIO 33 through
a 10k/20k divider (10k from OUT to GPIO 33, 20k from GPIO 33 to GND). This gives
an ADC divider ratio of 2/3 and keeps the ESP32 below its absolute input limit.
The module and ESP32 must share GND. Firmware calibrates the zero point at boot,
so the pump must remain off until `[OK] ACS712 ready` is printed.
