# HARDWARE INTEGRATION SPEC — Smart Water Leak Detection Rig

> Source of truth for firmware/backend/UI hardware integration, provided by the
> hardware owner. See `docs/CHANGELOG.md` for how this superseded the earlier
> `docs/MQTT_SPEC.md` payload shape and the SQLite-vs-MongoDB decision.

## 1. PHYSICAL SYSTEM

A closed-loop lab-scale water distribution rig.

```
Bucket -> Pump P1 -> [FLOW 1: Q_in] -> main line (10mm)
                                       |
                          +------------+------------+
                       [TEE A]      [TEE B]      [TEE C]
                        clamp        clamp        clamp     <- physical leak valves
                          +------------+------------+
                                       |
                          +------------+------------+
                    Branch A                   Branch B
                (servo pinch valve)          [FLOW 3: Q_branch]
                          +------------+------------+
                                       |
                                [FLOW 2: Q_out] -> Pump P2 -> back to bucket
```

P1 = supply pump (constant). P2 = demand generator, cycled to create
fluctuating background demand. Leaks are injected PHYSICALLY by opening a
calibrated screw clamp at a leak tee — there is no software leak injection on
real hardware.

## 2. COMPONENTS

| Component | Qty | Role |
|---|---|---|
| ESP32 DevKit v1 | 1 | sensor node, MQTT publisher |
| YF-S201 hall flow sensor | 3 | Q_in, Q_out, Q_branch |
| INA219 current sensor | 1 | pump P1 current, high-side on 12V line |
| 12V DC water pump | 2 | P1 supply, P2 demand |
| Relay module (active-LOW) | 2 | switch P1, P2 |
| Servo SG90/MG996R | 1 | pinch valve on Branch A |
| LM2596 buck converter | 1 | 12V -> 5.0V rail |
| 12V 2A adapter | 1 | supply |

## 3. PIN MAP — use these exact assignments

| Signal | GPIO | Notes |
|---|---|---|
| Flow 1 pulse (Q_in) | 34 | input-only, interrupt, RISING |
| Flow 2 pulse (Q_out) | 35 | input-only, interrupt, RISING |
| Flow 3 pulse (Q_branch) | 32 | interrupt, RISING |
| INA219 SDA | 21 | I2C, address 0x40 |
| INA219 SCL | 22 | |
| Relay 1 (Pump P1) | 25 | ACTIVE-LOW |
| Relay 2 (Pump P2) | 26 | ACTIVE-LOW |
| Servo PWM | 27 | 50Hz, LEDC channel |
| Status LED | 2 | onboard |

DO NOT USE: GPIO 6-11 (SPI flash, bricks boot), GPIO 0/2/12/15 (boot straps —
note GPIO2 is reused here as the onboard status LED, which is fine as an
output once boot has completed, but never drive it during boot-strap timing).

## 4. ELECTRICAL CONSTRAINTS THAT AFFECT FIRMWARE

- YF-S201 output is open-collector pulling to 5V; ESP32 is not 5V-tolerant.
  Hardware uses a 10k/20k divider per pulse line. No firmware action needed,
  but do not enable internal pull-ups on those pins.
- Servo is powered from the LM2596 5V rail, NOT ESP32 3V3. Firmware should
  still avoid rapid repeated servo commands that could cause current spikes.
- Relays are ACTIVE-LOW: `digitalWrite(pin, LOW)` energizes the coil and
  turns the pump ON. Initialize both pins HIGH at boot so pumps start OFF.
- INA219 measures pump P1 draw only. Expected range 400-900 mA when running,
  ~0 when off.

## 5. FIRMWARE REQUIREMENTS

The ESP32 is a SENSOR NODE ONLY. No detection logic, no thresholds, no
filtering on-device — all analysis happens in the Python backend.

### 5.1 Pulse counting

```cpp
volatile uint32_t pulse_in = 0, pulse_out = 0, pulse_br = 0;
void IRAM_ATTR isr_in()  { pulse_in++; }
void IRAM_ATTR isr_out() { pulse_out++; }
void IRAM_ATTR isr_br()  { pulse_br++; }
```

ISRs contain ONLY the increment — no Serial prints, no floats, no
arithmetic. `IRAM_ATTR` is mandatory on ESP32. Read counters inside
`portENTER_CRITICAL`/`portEXIT_CRITICAL`, snapshot and zero atomically.
Attach with RISING edge.

### 5.2 Flow conversion

```
Q_lpm = (pulses_in_window / K_factor) * (60 / window_seconds)
```

K_factor is PER SENSOR and comes from calibration — do NOT hardcode the
nominal 450. Store K1, K2, K3 in NVS/preferences so they can be updated
without reflashing. Default placeholders until calibration: K1=450.0,
K2=450.0, K3=450.0.

### 5.3 Telemetry — publish this exact schema at 1 Hz to topic `rig/telemetry`

```json
{
  "ts": 1754131200.123,
  "seq": 4471,
  "device": "esp32-rig-01",
  "flow": {
    "q_in_lpm": 4.812, "q_out_lpm": 4.655, "q_branch_lpm": 2.104,
    "pulses_in": 361, "pulses_out": 349, "pulses_branch": 158
  },
  "power": { "bus_v": 11.94, "current_ma": 842.3, "power_mw": 10056.0 },
  "actuators": { "pump1": true, "pump2": false, "servo_deg": 0 },
  "health": { "uptime_s": 4471, "wifi_rssi": -58, "free_heap": 184320 }
}
```

CRITICAL: publish RAW PULSE COUNTS alongside the converted L/min values. If
K-factor calibration turns out wrong later, every historical experiment can
be recomputed from raw counts instead of re-running physical tests. This is
non-negotiable.

### 5.4 Commands — subscribe to `rig/cmd`

```json
{ "pump1": true, "pump2": false, "servo_deg": 90 }
```

Servo actuates ONLY on explicit command, never autonomously.

### 5.5 Status — publish to `rig/status`, retained, with MQTT Last Will

Backend uses LWT to detect an offline device and show it in the UI.

### 5.6 Safety interlocks — must NOT depend on the network

- Pump watchdog: if no command received for 30 seconds, turn both pumps OFF.
  Prevents dry-running if WiFi drops.
- Hard cap on continuous pump runtime; requires explicit operator re-enable.
- Both relay pins initialized HIGH (pumps off) at boot, before WiFi connects.

### 5.7 Also produce a minimal `serial_test.ino`

Reads ONE sensor on GPIO 34 and prints the pulse count once per second over
serial. No WiFi, no MQTT, no I2C. This is the first hardware milestone and
must be trivially verifiable before anything else is wired.

## 6. CALIBRATION PARAMETERS THE BACKEND MUST CONSUME

These come from physical commissioning tests and MUST be configurable at
runtime, never hardcoded in application logic. Put them in `config.yaml` and
expose them in the UI's Calibration page.

| Param | Meaning |
|---|---|
| K1, K2, K3 | pulses per litre, per sensor, from volumetric calibration |
| bias | mean of R = Q_in - Q_out during a 30-min zero-leak run. Applied as a permanent correction: `R = Q_in - Q_out - bias` |
| sigma | std dev of that same residual. THE FOUNDATION OF DETECTION. Threshold = k * sigma. Flow-dependent — support sigma as a function of Q if multiple calibration points exist |
| k | sigma multiplier, default 3.0 |
| persistence_s | seconds the threshold must be exceeded before alarming, default 10 |
| clamp_calibration | per-tee lookup: `{tee_id, turns} -> leak_lpm`, e.g. `TEE_A: {0.25: 0.18, 0.5: 0.34, 0.75: 0.51, 1.0: 0.72, ...}`. The UI's leak-logging control must use this to auto-fill leak_lpm from the selected tee and turn count |

IMPORTANT: median detection latency can never be less than `persistence_s`.
Any UI showing latency below 10s with `persistence_s=10` is displaying
fabricated data.

## 7. WHAT THE BACKEND MUST DO WITH THIS

- Subscribe to `rig/telemetry`, persist every frame
- Compute residual `R = Q_in - Q_out - bias` (or `Q_in - (Q_out + Q_branch)`
  when the branch meter is in-loop — make which topology is active a config
  flag)
- Run 4 detectors: mass balance (k*sigma + persistence), current signature
  (I_residual vs fitted expected-current model), MNF (nonzero Q_in during a
  scripted low-demand window), CUSUM (change-point on R)
- Fuse into LOW/MEDIUM/HIGH confidence
- Push processed state to the frontend over WebSocket at 1 Hz
- Detect device offline via MQTT LWT and surface it in the UI

## 8. GROUND TRUTH LOGGING — the most important feature

Leaks are physical. The operator opens a real clamp. The software's only job
is to record the exact moment.

- The UI control must be labelled "LOG PHYSICAL LEAK EVENT", not "Inject
  Leak" — that implies software injection and contradicts the premise.
- Control captures: `tee_id` (A/B/C), `clamp_turns` (dropdown), auto-filled
  `leak_lpm` from the clamp calibration table, `demand_mode`
  (steady/variable), and a millisecond-precision timestamp on click.
- Writes to the `leak_events` table — the ground truth all metrics derive
  from. Treat it as the most important data in the system.
- Keep a SEPARATE, clearly-marked "simulate leak (mock data only)" control
  visible ONLY when running against the mock publisher, never against real
  hardware.

## 9. SIMULATION MODE

Until hardware is wired, the backend runs against a mock publisher emitting
the same schema (`tools/mock_publisher.py`).

- Show a persistent banner on every page: "SIMULATION MODE — synthetic
  telemetry, hardware integration pending"
- The banner must disappear automatically when frames arrive from a real
  `device_id`.
- Never render a plausible-looking fake number in place of missing data. Use
  an explicit empty state ("awaiting telemetry").

## 10. TASKS

1. `firmware/serial_test.ino` — single sensor, serial pulse count only
2. `firmware/main.ino` — full sensor node per section 5
3. `tools/mock_publisher.py` — emits the section 5.3 schema at 1 Hz
4. Backend ingestion + detection service per section 7
5. Section 6 parameters in `config.yaml`, wired to the Calibration UI page
6. Replace the "Inject Leak" buttons per section 8
7. Simulation-mode banner per section 9
8. Correct GPIO numbers shown anywhere in the UI to match section 3
