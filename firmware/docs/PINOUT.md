# Firmware Pinout Reference

```text
                  +--------------------+
                  |    ESP32 DEVKIT    |
                  |                    |
 Flow 1 interrupt | GPIO 34    GPIO 21 | INA219 / MPU6050 SDA
 Flow 2 interrupt | GPIO 35    GPIO 22 | INA219 / MPU6050 SCL
 Flow 3 interrupt | GPIO 32    GPIO 25 | Relay 1 (supply pump)
 Branch servo PWM | GPIO 27    GPIO 26 | Relay 2 (demand pump)
 Piezo ADC1       | GPIO 33     GPIO 4 | DS18B20 1-Wire
                  +--------------------+
```

Flow-sensor outputs require the documented level shifting because the ESP32 is
not 5 V tolerant. GPIO 34 and 35 are input-only, and the firmware deliberately
does not enable internal pull-ups on any flow input.

The current rig has no pressure transducer and no leak solenoid. Pressure shown
by the dashboard is explicitly labelled as an estimate; physical leak windows
are opened manually and recorded as operator ground truth.
