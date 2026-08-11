# HARDWARE INTEGRATION SPEC (v2) — Smart Water Leak Detection Rig

> Source of truth for firmware/backend/UI hardware integration. This is v2:
> three sensors (MPU6050, piezo, DS18B20) were added since v1, adding a fifth
> detection channel (acoustic). See `docs/CHANGELOG.md` for what changed.
>
> **Status (2026-08-09): all 9 tasks implemented.** Backend/frontend
> (tasks 3-9) verified with pytest, the self-test, `tsc --noEmit`, and a
> live browser check. Firmware (tasks 1-2) is written but **not compiled or
> flashed** — no PlatformIO toolchain available in the dev environment.
> `firmware/serial_test/serial_test.ino` is still the required first
> physical bring-up step before trusting `main.cpp`.

## 1. PHYSICAL SYSTEM

Closed-loop lab-scale water distribution rig.

```
Bucket -> Pump P1 -> [FLOW 1: Q_in] -> main line (10mm)
                                       |
                          +------------+------------+
                       [TEE A]      [TEE B]      [TEE C]
                        clamp        clamp        clamp    <- physical leak valves
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
fluctuating background demand. MPU6050 and piezo mounted on the pipe wall
near the leak tees. DS18B20 submerged in the reservoir. Leaks are injected
PHYSICALLY by opening a calibrated screw clamp — no software leak injection
on real hardware.

## 2. COMPONENTS

| Component | Qty | Role |
|---|---|---|
| ESP32 DevKit v1 | 1 | sensor node, MQTT publisher |
| YF-S201 hall flow sensor | 3 | Q_in, Q_out, Q_branch |
| INA219 current sensor | 1 | pump P1 current, high-side on 12V line |
| MPU6050 accelerometer | 1 | **NEW** — vibration/acoustic leak signature |
| Piezo disc | 2 | **NEW** — contact mic, secondary acoustic channel |
| DS18B20 temperature probe | 1 | **NEW** — water temp, K-factor compensation |
| 12V DC pump | 2 | P1 supply, P2 demand |
| 2-ch relay module (active-LOW) | 1 | switch P1, P2 |
| Servo MG996R | 1 | pinch valve on Branch A |
| LM2596 buck converter | 2 | #1 = 5.0V logic rail, #2 = 5.6V servo rail |
| 12V 2A adapter (Y-split) | 1 | pos1 -> bucks, pos2 -> switch -> relays |

## 3. PIN MAP — use these exact assignments

| Signal | GPIO | Notes |
|---|---|---|
| Flow 1 pulse (Q_in) | 34 | input-only, interrupt, RISING |
| Flow 2 pulse (Q_out) | 35 | input-only, interrupt, RISING |
| Flow 3 pulse (Q_branch) | 32 | interrupt, RISING |
| I2C SDA | 21 | INA219 @ 0x40, MPU6050 @ 0x68 |
| I2C SCL | 22 | |
| Relay 1 (Pump P1) | 25 | ACTIVE-LOW |
| Relay 2 (Pump P2) | 26 | ACTIVE-LOW |
| Servo PWM | 27 | 50Hz, LEDC |
| Piezo analog | 33 | ADC1 (safe with WiFi active) |
| DS18B20 1-Wire | 4 | requires 4.7k pull-up to 3.3V |

DO NOT USE: GPIO 6-11 (SPI flash, bricks boot), GPIO 0/2/12/15 (boot straps).

**No status LED.** Not wanted in firmware or UI — GPIO2 is not used for
anything in this revision.

## 4. ELECTRICAL CONSTRAINTS AFFECTING FIRMWARE

- YF-S201 output is open-collector to 5V; ESP32 is not 5V-tolerant. Hardware
  uses a 10k/20k divider per pulse line. Do NOT enable internal pull-ups on
  GPIO 34/35/32.
- Relays are ACTIVE-LOW: `digitalWrite(pin, LOW)` turns the pump ON.
  Initialize both pins HIGH at boot so pumps start OFF, before WiFi connects.
- Servo runs on a SEPARATE 5.6V rail (MG996R stall current 1.5-2.5A). Avoid
  rapid repeated servo commands. Never hold the pinch valve stalled longer
  than needed — close, settle ~15s, take reading, return to open.
- INA219 measures pump P1 only. Expect 400-900 mA running, ~0 when off.
- DS18B20 needs a 4.7k pull-up between data and 3.3V or 1-Wire will not
  enumerate.

## 5. FIRMWARE REQUIREMENTS

ESP32 is a SENSOR NODE. No detection logic, no thresholds, no alarm
decisions on-device — all analysis happens in the Python backend.

### 5.1 Pulse counting

```cpp
volatile uint32_t pulse_in = 0, pulse_out = 0, pulse_br = 0;
void IRAM_ATTR isr_in()  { pulse_in++; }
void IRAM_ATTR isr_out() { pulse_out++; }
void IRAM_ATTR isr_br()  { pulse_br++; }
```

ISRs contain ONLY the increment — no Serial, no floats, no arithmetic.
`IRAM_ATTR` mandatory. Read inside `portENTER_CRITICAL`/`portEXIT_CRITICAL`,
snapshot and zero atomically. Attach RISING.

### 5.2 Flow conversion

```
Q_lpm = (pulses_in_window / K_factor) * (60 / window_seconds)
```

K_factor is PER SENSOR, from volumetric calibration. Do NOT hardcode the
nominal 450. Store K1, K2, K3 in NVS/Preferences so they update without
reflashing. Placeholders until calibrated: 450.0 each.

### 5.3 Vibration — the one exception to "no on-device processing"

Acoustic data cannot be streamed at 1 Hz. Sample in bursts and publish only
summaries. This is BANDWIDTH REDUCTION, not detection logic — thresholds
stay in Python.

- Sample MPU6050 accelerometer in a burst: 512 samples @ 500 Hz (~1s)
- Configure DLPF for ~260 Hz bandwidth to prevent aliasing at that rate
- Compute RMS and band energies via FFT on-device: band_low 10-50 Hz,
  band_mid 50-150 Hz (leak jet energy concentrates here), band_high 150-250 Hz
- Piezo on GPIO 33: sample at 2 kHz for 0.25s, publish RMS and a simple
  spectral-centroid figure
- Publish only these summary values in the 1 Hz frame

**Mounting note for the physical build:** the MPU6050 must be rigidly
coupled to the pipe (zip-tie or epoxy, not tape) and mounted WELL DOWNSTREAM
of pump P1, whose vibration would otherwise swamp the leak signature.

### 5.4 Telemetry — publish this EXACT schema at 1 Hz to `rig/telemetry`

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
  "vibration": {
    "rms": 0.042,
    "band_low": 0.011, "band_mid": 0.087, "band_high": 0.203,
    "piezo_rms": 0.019, "piezo_centroid_hz": 143.2
  },
  "temp": { "water_c": 24.6 },
  "actuators": { "pump1": true, "pump2": false, "servo_deg": 0 },
  "health": { "uptime_s": 4471, "wifi_rssi": -58, "free_heap": 184320 }
}
```

CRITICAL: publish RAW PULSE COUNTS alongside converted L/min. If K-factor
calibration changes later, every historical experiment can be recomputed
from raw counts instead of re-running physical tests. Non-negotiable.

Implemented in `tools/mock_publisher.py` (task 3) — flags for leak
magnitude/timing, demand mode, flow noise, and acoustic
baseline/leak-elevation levels for all vibration/piezo fields.

### 5.5 Commands — subscribe to `rig/cmd`

```json
{ "pump1": true, "pump2": false, "servo_deg": 90 }
```

Servo actuates ONLY on explicit command, never autonomously.

### 5.6 Status — publish to `rig/status`, retained, with MQTT Last Will

Backend uses LWT to detect an offline device.

### 5.7 Safety interlocks — must NOT depend on the network

- Pump watchdog: no command in 30s => both pumps OFF (prevents dry-running
  on WiFi loss)
- Hard cap on continuous pump runtime, requires explicit operator re-enable
- Relay pins initialized HIGH (off) at boot, before WiFi connects

### 5.8 `firmware/serial_test/serial_test.ino`

ONE sensor on GPIO 34, pulse count printed once per second over serial. No
WiFi, no MQTT, no I2C. First hardware milestone, must be trivially
verifiable. **Unchanged by v2** — GPIO34/Q_in is unaffected by the new
sensors.

## 6. DETECTION — now FIVE channels

Backend computes residual `R = Q_in - Q_out - bias` (or
`Q_in - (Q_out + Q_branch)` when the branch meter is in-loop — topology is a
config flag, `backend/pipeline.py`'s `hydraulics.topology`).

1. **Mass balance** — alarm when `|R| > k*sigma` sustained for `persistence_s`
2. **Current signature** — `I_residual` vs a fitted expected-current model `I = f(Q_in, bus_v)`
3. **MNF** — nonzero Q_in during a scripted low-demand window
4. **CUSUM** — change-point on R, catches slow leaks below 3-sigma
5. **Acoustic (NEW)** — band_mid energy elevated vs a clean baseline spectrum

Fuse all five into a LOW/MEDIUM/HIGH confidence score. The acoustic channel
is PHYSICALLY INDEPENDENT of the flow and current channels — weight
agreement between independent physics more heavily than magnitude on any
single channel.

**Acoustic baseline:** band energies are meaningless in absolute terms.
Store a clean-running baseline spectrum per pump duty level during
calibration, and detect on the RATIO to baseline, not raw values.

**Temperature compensation:** DS18B20 water temp feeds a K-factor
correction. Pump warming causes viscosity change over a 2-hour run,
producing slow residual drift that would otherwise be misdiagnosed as a
leak. Make the correction coefficient configurable and default it to zero
until characterised.

## 7. CALIBRATION PARAMETERS — runtime-configurable, never hardcoded

| Param | Meaning |
|---|---|
| K1, K2, K3 | pulses per litre, per sensor |
| bias | mean of R during a 30-min zero-leak run; applied as `R = Q_in - Q_out - bias` |
| sigma | std dev of that same residual. THE FOUNDATION OF DETECTION. Threshold = k * sigma. Flow-dependent — support as a function of Q if multiple calibration points exist |
| k | sigma multiplier, default 3.0 |
| persistence_s | seconds above threshold before alarming, default 10 |
| vib_baseline | clean band energies per pump duty level |
| vib_ratio_threshold | band_mid ratio triggering the acoustic channel |
| temp_k_coeff | K-factor correction per degree C, default 0.0 |
| clamp_calibration | per-tee lookup `{tee_id, turns} -> leak_lpm`, e.g. `TEE_A: {0.25: 0.18, 0.5: 0.34, 0.75: 0.51, 1.0: 0.72}`. The leak-logging UI must auto-fill leak_lpm from tee + turns |

IMPORTANT: median detection latency can NEVER be less than `persistence_s`.

## 8. GROUND TRUTH LOGGING — the most important feature

Leaks are physical. The operator opens a real clamp. Software only records
the moment.

- UI control labelled "LOG PHYSICAL LEAK EVENT", not "Inject Leak" —
  implemented (`backend/api_server.py`'s `/api/ground-truth/start|stop`).
- Captures: `tee_id` (A/B/C), `clamp_turns` (dropdown), auto-filled
  `leak_lpm` from the clamp calibration table, `demand_mode`
  (steady/variable), millisecond timestamp on click.
- Writes to `leak_events` — the ground truth all reported metrics derive
  from. Treat it as the most important data in the system.
- A separate, clearly-marked "simulate leak (mock data only)" control is
  visible ONLY when running against the mock publisher, never against real
  hardware.

## 9. SIMULATION MODE

Until hardware is wired, the backend runs against `tools/mock_publisher.py`
emitting the same schema.

- Persistent banner on every page: "SIMULATION MODE — synthetic telemetry,
  hardware integration pending"
- Banner disappears automatically when frames arrive from a real `device_id`
- Never render a plausible-looking fake number for missing data — use an
  explicit empty state ("awaiting telemetry")

## 10. TASKS

1. `firmware/serial_test/serial_test.ino` — done, unaffected by v2
2. `firmware/src/main.cpp` — done: `vibration_sensor.{h,cpp}` (MPU6050 burst
   + on-device FFT), `piezo_sensor.{h,cpp}` (2kHz ADC burst + zero-crossing
   centroid), `temp_sensor.{h,cpp}` (DS18B20). Wired into `main.cpp` on a
   5s cadence (both bursts block ~1s/~0.25s, too slow for every 1Hz tick),
   cached and republished between bursts. **Not compiled or flashed — no
   PlatformIO toolchain in the dev environment. Verify on real hardware
   before trusting it.**
3. `tools/mock_publisher.py` — done, emits section 5.4 schema incl.
   vibration/temp fields
4. Backend: five-channel detection (acoustic added), fusion reweighting
   (32/20/16/12/20% + independent-agreement bonus), temperature
   compensation (default 0.0 no-op) — done, verified with pytest +
   a manual pipeline run confirming acoustic fuses correctly with
   flow/current evidence
5. Section 7 calibration params in `config.yaml` (`thresholds.yaml`'s
   `acoustic:` block) + Calibration UI (`vib_baseline_band_mid`,
   `temp_k_coeff` fields) — done, verified via live save/readback
6. "LOG PHYSICAL LEAK EVENT" ground-truth UI — done
   (`/api/ground-truth/*`)
7. Simulation-mode banner — done (`src/App.tsx`)
8. Correct GPIO numbers shown in UI to match section 3 — done
   (`docs/PROJECT_CONTEXT.md`'s hardware table was still on the old wrong
   pins; `CalibrationView.tsx` was already correct)
9. Vibration spectrum panel in UI — done
   (`DetectionEngineView.tsx`, band bars + ratio-to-baseline, honest empty
   state when no acoustic data present)

**Note:** persistence remains MongoDB (`docs/DECISIONS.md` #001), not
SQLite. `backend/storage/schema.sql` is a stale, unused artifact — see
`docs/CHANGELOG.md`. This spec's task list mentions SQLite; flagged for
confirmation before task 4 proceeds.
