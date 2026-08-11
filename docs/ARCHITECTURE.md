# ARCHITECTURE

## System Architecture

```text
TWO OPERATING MODES — identical after ingestion (docs/OPERATING_MODES.md)

  Mock Data Mode                    Live Sensor Mode
  MockTelemetrySource               ESP32 Rig Sensors
  (declarative scenarios)           (Flow1/2/3, INA219, Pressure, Solenoid)
        │                                   │ [MQTT: rig/telemetry]
        │                            Mosquitto Broker
        │                                   │
        └───────────┬───────────────────────┘
                    ↓
          TelemetryIngestor  (ONE shared path)
            validate → TelemetryDTO → DetectionPipeline
                    ↓
 Python / Express Backend
  ├── Telemetry Collector & Validator
  ├── MongoDB Database Layer (mongodb://localhost:27017/water_leak_detection)
  ├── Multi-Algorithm Detectors:
  │    ├── Mass Balance
  │    ├── Current Signature
  │    ├── Minimum Night Flow (MNF)
  │    └── CUSUM
  ├── Multi-Sensor Fusion Engine
  ├── Replay Engine
  ├── Branch Localization Engine
  └── CP-SAT Work Order Scheduler
        ↓
 Web Workbench & Live Dashboard
```

## Core Architecture Principles

1. **One-Way Data Flow**:
   - `ESP32` -> `MQTT` -> `Collector` -> `MongoDB` -> `Detectors` -> `Dashboard`
   - No circular dependencies or backward mutation chains.

2. **Every Layer Testable Independently**:
   - ESP32 tested with MQTT Explorer
   - MQTT tested with mock publisher script
   - MongoDB tested with mongo shell / pymongo scripts
   - Detector tested with CSV/JSON benchmark datasets
   - Dashboard tested with sample database

3. **No Microservices**:
   - Flat single-process backend architecture for immediate debugging and low overhead.

4. **Single Source of Truth**:
   - MongoDB database is the sole authority for telemetry collections, detection records, and experiment runs.

