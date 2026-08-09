# Smart Water Leak Detection

An explainable hardware-in-the-loop platform for detecting and localizing
probable water leaks from flow imbalance, pump-current signatures, CUSUM drift,
and minimum-night-flow evidence.

Confirmed live incidents can optionally send one deduplicated Twilio WhatsApp
Content Template message. Credentials remain in `.env`, and replay notifications
are disabled by default. See `docs/WHATSAPP_ALERTS.md`.

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
- Impact analysis, an Alert Center, and printable experiment reports are built
  dependency-free — no extra packages beyond `requirements.txt`.

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
```

This installs Express, React 19, Recharts, Lucide React, Vite, Tailwind CSS,
motion, tsx, and type declarations.

### Python backend dependencies

Create a virtual environment first. This is **required**, not optional: modern
Homebrew/Debian Python installs are PEP 668 "externally managed" and will
refuse a bare `pip install` with an `externally-managed-environment` error.

```bash
python3 -m venv .venv
```

Activate it (do this in every new terminal you run backend commands from):

```bash
source .venv/bin/activate
```

Then install the required Python packages:

```bash
pip install -r requirements.txt
python scripts/init_db.py
```

> Activating the venv is also what makes the bare `python` command in this
> README resolve — macOS ships `python3` only, so an unactivated shell fails
> with `command not found: python`. On Windows the activate command is
> `.venv\Scripts\activate`.

*Required Python libraries installed:*
* `pyyaml`: Configuration parsing
* `paho-mqtt`: MQTT communication client
* `pymongo`: Database operations
* `pydantic`: DTO schema validation
* `numpy` / `scipy`: Numerical processing & analytics
* `fastapi` / `uvicorn`: Detection API service (`backend/api_server.py`)
* `openai`: Azure OpenAI work-order summaries (optional — falls back to
  deterministic templates when `AZURE_OPENAI_API_KEY` is unset)

## 🚀 Quick start (replay mode — no hardware required)

`npm run dev` (`scripts/dev.mjs`) starts **both** processes together: the
Python detection API on port `8001` and the Express/Vite web server on port
`3000`, with combined logs and a shared shutdown on Ctrl+C. Express is only a
thin proxy — if the Python service fails to start, every view returns
`502 Detection backend unreachable` and renders empty; check the API's half of
the combined log output first.

Make sure MongoDB is running first (`brew services start mongodb-community` on
macOS), and that your virtual environment is activated
(`source .venv/bin/activate`), then from the repository root:

```bash
python -m backend.replay.seed_runs   # 300 samples + a ground-truth leak window,
                                      # so Replay mode has real data before any
                                      # hardware exists
npm run dev
```

Or do both in one command: `npm run demo`.

Open **http://localhost:3000**. The system defaults to Replay mode and loops
the seeded run through the real detection pipeline, so leak alerts, severity,
and cost impact appear on their own roughly every 75 seconds.

> Port `8001`, not `8000` — on at least one dev machine an unrelated app was
> already bound to `8000`, so `8001` is the project default everywhere
> (`.env.example`, `scripts/dev.mjs`, `backend/api_server.py`). Override with
> `API_PORT` / `PORT` / `FASTAPI_BASE_URL` in `.env` if your setup differs.

> **Run `npm run dev` from the repository root.** `config_loader.py` resolves
> `backend/config/*.yaml` by relative path, so an API process launched from
> inside `backend/` silently falls back to hardcoded defaults instead of your
> YAML — `scripts/dev.mjs` already does this correctly.

> **Live mode requires an MQTT broker** on port `1883`
> (`brew install mosquitto && brew services start mosquitto`). Without it the
> backend logs a single startup warning and Replay mode works normally — this
> is not a failure. Live and Replay run through the identical
> `DetectionPipeline`.

## Running commands

### 1. System self-diagnostic test

Before starting the web app or connecting hardware, verify all backend
modules (Config Loader, Telemetry Validator, Detector Engine, State Machine,
Fusion & Confidence Engine, Localization Service):

```bash
python backend/self_test/system_self_test.py
```

### 2. Hardware unit test scripts

Test individual sensor and actuator interfaces:

```bash
python tests/test_flow1.py    # YF-S201 Flow Sensor #1 calculation logic
python tests/test_ina219.py   # INA219 Motor Current & Voltage sampling logic
python tests/test_servo.py    # Servo Motor isolation PWM commands
python tests/test_pump.py     # Relay Pump toggle signals
```

### 3. Backend logic test suites

Unit tests for the detection and impact logic (these need no hardware; the
alert tests need no MongoDB either):

```bash
python -m pytest -q
# or: python -m unittest discover -s tests -p "test_*.py"
```

Covers the 3-sigma mass balance detector, CUSUM recovery, localization
baseline tracking, topology-aware residuals, the hardware-owner MQTT packet
and legacy packet compatibility, the impact arithmetic (water loss, cost,
severity bands, progression), and the alert lifecycle (incident merging,
replay idempotency, savings crediting, query filters).

### 4. Build for production

Compile the React client assets and bundle `server.ts` into a standalone
CommonJS bundle (`dist/server.cjs`):

```bash
npm run build
npm run start
```

## Deterministic demo dataset

```bash
npm run demo
```

Runtime values can be copied from `.env.example`. Defaults are FastAPI
`8001`, web `3000`, MongoDB `27017`, and MQTT `1883`.

## Verify before a demo

```bash
python -m pytest -q
python backend/self_test/system_self_test.py
npm run lint
npm run build
```

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
