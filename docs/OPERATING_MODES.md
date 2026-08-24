# Operating Modes

Jal Netra has exactly two operating modes. They change the source and storage
of telemetry, not how a sample is detected.

| Concern | Mock Data Mode | Live Sensors Mode |
|---|---|---|
| Source | Seeded declarative scenarios and manual mock injection | ESP32 over local MQTT |
| Wire input | Canonical nested document | Nested document or upstream flat ESP32 packet |
| Database | `jal_netra_mock` | `jal_netra_live` |
| Ground truth | Scenario leak windows | Operator-timestamped physical clamp windows |
| Notifications | Off unless explicitly opted in | WhatsApp may notify when configured |
| Hardware commands | None | Firmware-supported pump/servo commands only |

## Shared processing contract

Both inputs pass through a wire adapter and become the same nested
`TelemetryDTO`. That DTO enters one validator, one `TelemetryIngestor`, and one
DTO-only `DetectionPipeline`. Mass balance, current signature, CUSUM, minimum
night flow, acoustic plausibility, fusion, confidence, localization, alerting,
impact, and reports are therefore identical across modes.

The current nested contract is canonical for storage and new firmware. The flat
adapter is intentionally retained so the upstream ESP32 firmware can connect
without duplicating or weakening the downstream pipeline.

## Live rig truth

The current bring-up profile has three flow meters and one MPU6050
acoustic/vibration sensor, sampled by the ESP32 and published every five
seconds. INA219, piezo and DS18B20 readings are explicitly unavailable rather
than replaced with zeroes. Missing channels are removed from fusion and the
remaining weights are renormalised. The rig has no pressure transducer,
electronic leak valve, or air-bubble actuator.

Localization retains learned Branch B baseline shifts and Branch A servo
isolation. The topology cannot distinguish a separate `Branch_C` output, so an
unisolated event remains `Main_Trunk` with an evidence-qualified confidence.

## Mode switching

Switching mode resets all stateful detectors and localization baselines. Mock
and live alerts are held by different service instances as well as different
databases, so synthetic incidents cannot contaminate live operational KPIs.
The offline benchmark scorer is an analysis tool, not a third operating mode.
