# FIRMWARE PINOUT REFERENCE

```
                +--------------------+
                |    ESP32 DEVKIT    |
                |                    |
 Flow 1 Interrupt | GPIO 34    GPIO 21 | INA219 SDA
 Flow 2 Interrupt | GPIO 35    GPIO 22 | INA219 SCL
 Flow 3 Interrupt | GPIO 32    GPIO 25 | Relay 1 (Pump)
 Branch Servo PWM | GPIO 27    GPIO 26 | Relay 2 (Pump P2)
                  +--------------------+
```
