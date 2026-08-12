# ARCHITECTURAL DECISIONS

## Decision #001: MongoDB over SQLite / Relational
- **Date**: 2026-08-03
- **Status**: Approved
- **Context**: Need durable, high-speed, schema-flexible document storage for 1Hz telemetry streaming, nested detection documents, and replay logs.
- **Decision**: Use MongoDB with physically separate `jal_netra_live` and
  `jal_netra_mock` databases.
- **Consequences**: Dynamic JSON document structure; fast timestamp index scans (`{ ts: -1 }`); effortless query expansion without migration scripts.


## Decision #002: Flat Backend Services
- **Date**: 2026-08-03
- **Status**: Approved
- **Context**: Avoid distributed microservice overhead during 2-week development cycle.
- **Decision**: Single Python / Node backend containing ingestion, storage,
  detectors, offline benchmark scoring, and scheduler modules.
- **Consequences**: Debugging takes seconds; zero network delay between ingestion and detection.

## Decision #003: Multi-Sensor Confidence Fusion
- **Date**: 2026-08-03
- **Status**: Approved
- **Context**: Single detector (e.g. Mass Balance) suffers false positives during pump startup transients.
- **Decision**: Combine Mass Balance, Motor Current, MNF, CUSUM, and optional
  acoustic evidence into a weighted confidence index, with a physical
  plausibility guard for contradictory sensor behavior.
- **Consequences**: Multiple methods can corroborate a leak, but published
  false-positive rates remain illustrative until measured on labelled rig data.

## Decision #004: Two Inputs, One Canonical Telemetry Contract
- **Date**: 2026-08-11
- **Status**: Approved
- **Context**: The PR's mock path uses nested telemetry, while upstream ESP32
  integrations may publish flat sensor fields and hardware metadata. Competing
  pipeline signatures (`voltage_v` versus `bus_v`) allowed the paths to drift.
- **Decision**: Retain both Mock Data and Live Sensors modes. Normalize nested
  and flat wire packets through explicit adapters into the nested
  `TelemetryDTO`; make `DetectionPipeline.process_sample()` DTO-only. Treat the
  nested contract as canonical for storage and new firmware, while retaining
  the flat adapter as a supported hardware migration boundary.
- **Consequences**: Both modes share validation, detection, plausibility,
  localization, alerting, work orders, and reporting. Wire compatibility is
  isolated to ingestion instead of duplicated throughout the application.

## Decision #005: Physical Rig Capabilities Are Authoritative
- **Date**: 2026-08-11
- **Status**: Approved
- **Context**: Older UI/API code referenced pressure sensors, leak solenoids,
  and air-bubble actuators that are not present and are not accepted by the
  current ESP32 firmware.
- **Decision**: Keep acoustic/current plausibility, learned Branch B baselines,
  Branch A servo isolation, raw pulse and hardware-health metadata, CP-SAT
  scheduling, and WhatsApp notification. Remove pressure/solenoid assumptions
  and remote live leak injection. Live leak ground truth is an operator-logged
  physical clamp window; MQTT commands use only firmware-supported fields.
- **Consequences**: Mock mode remains fully interactive, while Live mode is an
  honest hardware diagnostic interface and cannot imply unsupported actuation.
