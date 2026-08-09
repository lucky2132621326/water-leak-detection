# Smart Water Leak Detection

An explainable hardware-in-the-loop platform for detecting and localizing
probable water leaks from flow imbalance, pump-current signatures, CUSUM drift,
and minimum-night-flow evidence.

This is decision-support software: every result includes confidence, evidence,
a false-positive warning, and a field-verification requirement. The dashboard
does not expose operational pump or valve controls.

## What makes the system credible

- One detection pipeline for ESP32 live telemetry and historical replay.
- Exact raw pulse counts are stored beside converted flow values.
- Four independent detectors feed a weighted sensor-fusion decision.
- Leak likelihood, time window, suspected zone, and evidence are returned in a
  stable API contract.
- Physical leak start/stop is logged separately as millisecond-precision ground
  truth for precision, recall, F1, and detection-latency measurement.
- MQTT Last Will, device freshness, MongoDB health, and simulation/live state
  are visible rather than replaced by plausible fake values.
- Firmware safety is local: pumps boot OFF, incomplete commands are rejected,
  and command/runtime watchdogs do not depend on the network.

## Architecture

```text
ESP32 sensors (3× flow + INA219 + actuator state)
                    │  MQTT / rig/telemetry @ 1 Hz
                    ▼
FastAPI ingestion → validation → MongoDB + JSONL evidence log
                    │
                    ├─ mass balance (bias + persistence)
                    ├─ motor-current signature
                    ├─ CUSUM change detection
                    └─ minimum night flow
                    │
                    ▼
       fusion → confidence → localization → work-order brief
                    │
                    ▼
             React decision-support dashboard
```

The physical topology is `recombined_branch`: Branch A and B rejoin before
`Q_out`, so `Q_branch` is a localization/demand feature and is not subtracted a
second time from the main mass balance. See
[`docs/HARDWARE_INTEGRATION_SPEC.md`](docs/HARDWARE_INTEGRATION_SPEC.md).

## Quick start

Requirements: Node.js 18+, Python 3.9+, MongoDB, and (for live hardware or the
mock MQTT stream) a Mosquitto-compatible broker on port 1883.

```bash
npm install
python -m pip install -r requirements.txt
python scripts/init_db.py
```

Start the Python detection API and React/Express application together:

```bash
npm run dev
```

Open `http://localhost:3000`. A seeded `RUN_001` will replay automatically when
it exists. To recreate the deterministic demo dataset first:

```bash
npm run demo
```

Runtime values can be copied from `.env.example`. Defaults are FastAPI `8001`,
web `3000`, MongoDB `27017`, and MQTT `1883`.

## Verify before a demo

```bash
python -m pytest -q
python backend/self_test/system_self_test.py
npm run lint
npm run build
```

The Python suite covers the hardware-owner MQTT packet, legacy packet
compatibility, topology-aware residuals, detector recovery, localization, and
hardware calculation helpers.

## ESP32 commissioning order

1. Wire only Flow 1 to GPIO 34 through the required level divider.
2. Flash `firmware/serial_test/serial_test.ino` and verify pulses once per
   second before connecting Wi-Fi, MQTT, relays, or I2C.
3. Copy `firmware/src/secrets.example.h` to the Git-ignored `secrets.h`; set the
   demo Wi-Fi and the laptop's LAN address as `MQTT_BROKER`.
4. Build and flash `firmware/` with PlatformIO.
5. Verify retained `rig/status`, then inspect one `rig/telemetry` packet against
   [`docs/MQTT_SPEC.md`](docs/MQTT_SPEC.md).
6. Confirm both active-low pump relays boot OFF and the 30-second watchdog turns
   them off without a fresh supervised command.
7. Run a zero-leak calibration before trusting thresholds or latency metrics.

```bash
pio run -d firmware
pio run -d firmware --target upload
pio device monitor -d firmware
```

## Mock hardware stream

The mock publisher uses the exact nested hardware schema and identifies itself
as `mock-rig-01`, allowing the UI to remain visibly in simulation mode.

```bash
python tools/mock_publisher.py --duration-s 120
python tools/mock_publisher.py --leak-lpm 0.5 --leak-start-s 30 --leak-duration-s 45
```

Mock frames are never counted as physical evidence in the independent live
JSONL hardware log.

## MQTT topics

- `rig/telemetry`: nested sensor frame at 1 Hz, QoS 1, not retained.
- `rig/status`: device state/health, retained, with an `OFFLINE` Last Will.
- `rig/cmd`: supervised lab-rig command containing all of `pump1`, `pump2`, and
  `servo_deg`; firmware rejects partial commands.

The canonical schemas are in [`docs/MQTT_SPEC.md`](docs/MQTT_SPEC.md). Network
credentials live only in `firmware/src/secrets.h`, which is excluded from Git
and from the dashboard's repository viewer.

## Safety and interpretation

- A high likelihood is not proof of a leak.
- Field verification is required before repair or isolation work.
- Estimated pressure is clearly tagged because the current rig has no pressure
  transducer.
- The public dashboard provides no operational valve-control instructions.
- Physical ground-truth logging is enabled only when a fresh, non-mock ESP32
  stream is active in live mode.
