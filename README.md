# Water Leak Detection System (Hardware-In-The-Loop & Analytics Workbench)

A high-reliability, real-time water pipeline leak detection system combining physical test rig telemetry (ESP32), multi-algorithm sensor fusion (Mass Balance, Current Signature, CUSUM, MNF), explainable confidence evaluation, branch isolation localization, and a full-stack Web Workbench & Dashboard.

---

## 🛠️ Prerequisites & Installation Requirements

Before running the application or physical rig components, ensure the following prerequisites are installed on your environment:

### 1. System Runtime Requirements
* **Node.js**: `v18.x` or `v20.x` (LTS recommended)
* **npm**: `v9.x` or higher
* **Python**: `3.9+` (with `pip` package manager)
* **Docker Desktop**: provides MongoDB (and optionally the MQTT broker) via
  `docker-compose.yml` — see Step 3. Install from
  [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
  or `brew install --cask docker`.
* **Firmware (Optional for Physical Rig)**: PlatformIO CLI or Arduino IDE with ESP32 board support packages

> **MongoDB and Mosquitto are no longer installed per-machine.** They run as
> containers so every developer gets identical versions with one command. A
> pre-existing Homebrew install still works — Docker publishes the same default
> ports — but the two cannot run at once (see Troubleshooting).

---

## 📦 Installation Guide

### Step 1: Install Node.js Dependencies (Dashboard & Server)

In the project root directory, run:

```bash
npm install
```

This installs Express, React 19, Recharts, Lucide React, Vite, Tailwind CSS, motion, tsx, and type declarations.

---

### Step 2: Install Python Backend Dependencies

Create a virtual environment first. This is **required**, not optional: modern
Homebrew/Debian Python installs are PEP 668 "externally managed" and will refuse
a bare `pip install` with an `externally-managed-environment` error.

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
```

> Activating the venv is also what makes the bare `python` command in this
> README resolve — macOS ships `python3` only, so an unactivated shell fails
> with `command not found: python`. On Windows the activate command is
> `.venv\Scripts\activate`.

---

### Step 3: Start MongoDB (Docker)

With Docker Desktop running, bring up the database from the project root:

```bash
docker compose up -d
```

This starts MongoDB 7.0 as container `wld-mongo`, published on the standard
`localhost:27017`. Data persists in a Docker named volume (`mongo_data`), so it
survives restarts and `docker compose down`.

Confirm it is accepting connections:

```bash
docker compose ps
```

`STATUS` should read `Up ... (healthy)`. To block until it is ready — useful in
scripts and CI — start it with `docker compose up -d --wait` instead.

**Optional — MQTT broker for Live Sensor Mode.** Mock Data Mode, the dashboard
and the whole test suite do not need this, so it is behind a profile and stays
stopped unless you ask for it:

```bash
docker compose --profile live up -d
```

> **No application configuration is required.** `backend/repositories/db.py`
> already defaults to `mongodb://localhost:27017`, which is exactly what the
> container publishes. Set `MONGO_URI` only if you deliberately remap the port.

*Required Python libraries installed:*
* `pyyaml`: Configuration parsing
* `paho-mqtt`: MQTT communication client
* `pymongo`: Database operations
* `pydantic`: DTO schema validation
* `numpy` / `scipy`: Numerical processing & analytics
* `fastapi` / `uvicorn`: Detection API service (`backend/api_server.py`)
* `openai`: Azure OpenAI work-order summaries (optional — falls back to
  deterministic templates when `AZURE_OPENAI_API_KEY` is unset)

> **No additional packages are needed for the impact analysis, Alert Center or
> automatic experiment reports.** Those were built deliberately dependency-free:
> reports render as printable HTML with hand-rolled inline SVG charts rather than
> pulling in a PDF/plotting toolchain, so `requirements.txt` is unchanged.

---

## 🚀 Quick Start (Mock Data Mode — no hardware required)

The dashboard needs **two processes**: the Python detection API on port `8000`
and the Express/Vite web server on port `3000`. Express is only a thin proxy —
if the Python service isn't running, every view returns
`502 Detection backend unreachable` and renders empty.

Make sure MongoDB is running (`docker compose up -d`, see Step 3) and your
virtual environment is activated (`source .venv/bin/activate`, see Step 2),
then:

**Step 1 — start the detection API** (terminal 1):

```bash
python -m uvicorn backend.api_server:app --host 127.0.0.1 --port 8000 --reload
```

**Step 2 — start the dashboard** (terminal 2):

```bash
npm run dev
```

Open **http://localhost:3000**. The system boots into **Mock Data Mode** and
streams a generated leak scenario through the real detection pipeline, so leak
alerts, severity and cost impact appear on their own.

Use the **Mock Scenarios** tab to pick a different scenario (small/large/gradual
leak, branch-specific, night flow, sensor faults) or to score all ten against
their known ground truth. Switch to **Live Sensor Mode** from the header badge
once a rig is publishing — everything after ingestion is the identical pipeline.
See `docs/OPERATING_MODES.md`.

> **Run both commands from the repository root.** `config_loader.py` resolves
> `backend/config/*.yaml` by relative path, so launching uvicorn from inside
> `backend/` silently falls back to hardcoded defaults instead of your YAML.

> **Live Sensor Mode requires an MQTT broker** on port `1883`
> (`docker compose --profile live up -d`). Without it the backend reports the
> broker unreachable and Mock Data Mode works normally — this is not a failure.

### Stopping

Stop the app servers with `Ctrl+C` in each terminal. Then stop the containers:

```bash
docker compose down
```

Your database is preserved. To wipe it entirely (Mock Data Mode regenerates its
own scenarios, so nothing needs re-seeding) use:

```bash
docker compose down -v
```

---

## 🚀 Running Commands

### 1. System Self-Diagnostic Test
Before starting the web app or connecting hardware, verify all backend modules (Config Loader, Telemetry Validator, Detector Engine, State Machine, Fusion & Confidence Engine, Localization Service):

```bash
python backend/self_test/system_self_test.py
```

---

### 2. Hardware Unit Test Scripts
Test individual sensor and actuator interfaces:

```bash
# Test YF-S201 Flow Sensor #1 calculation logic
python tests/test_flow1.py

# Test INA219 Motor Current & Voltage sampling logic
python tests/test_ina219.py

# Test Servo Motor isolation PWM commands
python tests/test_servo.py

# Test Relay Pump toggle signals
python tests/test_pump.py
```

---

### 3. Backend Logic Test Suites

Unit tests for the detection and impact logic (these need no hardware; the
alert tests need no MongoDB either):

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Covers the 3-sigma mass balance detector, the impact arithmetic (water loss,
cost, severity bands, progression) and the alert lifecycle (incident merging,
replay idempotency, savings crediting, query filters).

---

### 4. Start Development Web Workbench (Full-Stack Express + Vite)

Serves the React dashboard and proxies `/api/*` to the Python detection service:

```bash
npm run dev
```

* Access the live dashboard at: `http://localhost:3000`
* **Requires `backend.api_server` running on port `8000`** — see Quick Start
  above. Express does not evaluate telemetry itself; it forwards every API call.

---

### 5. Build for Production

To compile the React client assets and bundle `server.ts` into a standalone CommonJS bundle (`dist/server.cjs`):

```bash
npm run build
```

---

### 6. Start Production Server

Launch the compiled production bundle:

```bash
npm run start
```

---

## ⚙️ Configuration Setup

System parameters and thresholds are dynamically configured in `backend/config/settings.yaml`:

```yaml
mqtt:
  host: "localhost"
  port: 1883
  topic: "rig/telemetry"
  cmd_topic: "rig/cmd"

database:
  uri: "mongodb://localhost:27017"
  name: "water_leak_detection"

detector:
  sigma_multiplier: 3.0
  persistence_seconds: 10
  bias_lpm: 0.10
  current_drop_threshold_ma: 20.0
  cusum_slack_k: 0.15
  cusum_decision_h: 3.0
```

> **Careful with `database.uri`:** `backend/repositories/db.py` reads the
> `MONGO_URI` **environment variable** (falling back to
> `mongodb://localhost:27017`) and does *not* consult this YAML block. Editing
> `database.uri` here has no effect on where the backend actually connects. The
> default already matches what `docker compose up -d` publishes, so for normal
> development neither needs touching.

---

## 🔌 Hardware Setup & Firmware Flashing

1. Connect ESP32 DevKit V1 to (see `docs/HARDWARE_SETUP.md` / `firmware/docs/PINOUT.md` — source of truth, matches `firmware/src/config.h`):
   - **YF-S201 Flow Sensors**: GPIO 34 ($Q_{\text{in}}$), GPIO 35 ($Q_{\text{out}}$), GPIO 32 ($Q_{\text{branch}}$)
   - **INA219 Current Sensor**: I2C SDA (GPIO 21) / SCL (GPIO 22)
   - **Relays (Pump / Leak Solenoid)**: GPIO 25 & GPIO 26
   - **Servo Isolation Actuator**: PWM GPIO 27
   - No physical pressure sensor is installed; `pressure_bar` is estimated server-side from flow/pump state.
2. Open `firmware/` in PlatformIO (`platformio.ini` targets `esp32dev`).
3. `pio run --target upload` to flash, `pio device monitor` to view logs.
