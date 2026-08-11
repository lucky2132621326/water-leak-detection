# FIRMWARE PINOUT REFERENCE

```
                +--------------------+
                |    ESP32 DEVKIT    |
                |                    |
 Flow 1 Interrupt | GPIO 34    GPIO 21 | INA219 SDA
 Flow 2 Interrupt | GPIO 35    GPIO 22 | INA219 SCL
 Flow 3 Interrupt | GPIO 32    GPIO 25 | Relay 1 (Pump)
 Valve Servo PWM  | GPIO 27    GPIO 26 | Relay 2 (Solenoid)
 Pressure (ADC1) | GPIO 36            |
                  +--------------------+
```


## Pressure Transducer (GPIO 36 / ADC1_CH0)

Analog ratiometric water-pressure sender, typically 0.5–4.5 V over 0–1.2 MPa.

**A voltage divider is mandatory.** The sensor swings to 4.5 V; ESP32 ADC pins
are 3.3 V tolerant and connecting it directly will damage the pin.

```
Sensor OUT ---[ 10k ]---+--- GPIO 36
                        |
                      [ 20k ]
                        |
                       GND
```

That divider gives `Vadc = Vout x 20/(10+20) = Vout/1.5`, so 4.5 V arrives as
3.0 V — inside range with headroom. `PRESSURE_DIVIDER_RATIO` in `config.h` must
match the resistors actually fitted (1.5 for 10k/20k); if it does not, every
pressure reading is proportionally wrong.

GPIO 36 is chosen deliberately: it is input-only and sits on **ADC1**, which
keeps working while WiFi is active. ADC2 pins are unusable whenever the radio
is on, which would silently break pressure readings only after the rig connects.

### Calibration

1. With the system at rest and open to atmosphere, note the reported bar. It
   should read ~0. A large offset means `PRESSURE_V_MIN` is wrong for your part.
2. Compare against a reference gauge at a known working pressure and adjust
   `PRESSURE_MAX_BAR` until they agree.
3. Confirm `pressure_bar` appears in the MQTT payload. If the key is missing,
   the transducer is reading below its 0.5 V floor — check power and wiring
   before suspecting the backend.
