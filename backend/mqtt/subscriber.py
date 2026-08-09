"""MQTT Telemetry Subscriber

Live-mode ingestion: subscribes to rig/telemetry, validates each payload,
runs it through the shared DetectionPipeline, persists telemetry + the
shaped response to MongoDB, and hands the latest response to whatever
process is asking (the FastAPI service, via `latest_response`).

Run standalone with: python -m backend.mqtt.subscriber
"""
import json
import threading
import time
import paho.mqtt.client as mqtt

from backend.config.config_loader import config_loader
from backend.validators.telemetry_validator import TelemetryValidator
from backend.models.telemetry import TelemetryDTO
from backend.repositories.telemetry_repository import TelemetryRepository
from backend.repositories.detection_repository import DetectionRepository
from backend.repositories.file_logger import log_frame
from backend.pipeline import DetectionPipeline
from backend.response.response_builder import build_response
from backend.utils.logger import logger


class LiveTelemetryIngestor:
    """Owns the live-mode pipeline state and the most recent shaped response,
    so the FastAPI layer can read `latest_response` without touching MQTT."""

    def __init__(self):
        self.pipeline = DetectionPipeline()
        self.telemetry_repo = TelemetryRepository()
        self.detection_repo = DetectionRepository()
        self.latest_response = None
        self.latest_telemetry = None
        self.latest_status = None
        self.latest_received_at = None
        self.samples_received = 0
        self.latest_is_simulation = False
        self._fallback_seq = 0
        self._lock = threading.Lock()

    def handle_payload(self, raw: dict):
        normalized = dict(raw)

        # Older firmware used uptime seconds until NTP synchronized and did not
        # include a sequence number. Preserve that device value for diagnosis,
        # but use server receive time so MNF/time-window logic stays correct.
        device_ts = normalized.get("ts")
        if isinstance(device_ts, (int, float)) and device_ts < 1_700_000_000:
            normalized["device_ts"] = device_ts
            normalized["ts"] = int(time.time())
            normalized["ts_source"] = "server_received"
        else:
            normalized["ts_source"] = "device_ntp"

        if "seq" not in normalized:
            normalized["seq"] = self._fallback_seq
        self._fallback_seq = max(self._fallback_seq + 1, int(normalized.get("seq", 0)) + 1)

        is_valid, msg = TelemetryValidator.validate(normalized)
        if not is_valid:
            logger.warning(f"[MQTT] Rejected telemetry: {msg}")
            return

        dto = TelemetryDTO.from_dict(normalized)
        is_simulation = dto.device_id.lower().startswith(("mock", "sim"))
        pump_on = dto.actuators.pump1 or dto.actuators.pump2

        result = self.pipeline.process_sample(
            ts=dto.ts,
            q_in=dto.flow.q_in_lpm,
            q_out=dto.flow.q_out_lpm,
            q_branch=dto.flow.q_branch_lpm,
            current_ma=dto.power.current_ma,
            voltage_v=dto.power.voltage,
            pump_on=pump_on,
            servo_state_deg=dto.actuators.servo_deg,
        )
        response = build_response(result)

        with self._lock:
            self.latest_response = response
            self.latest_telemetry = normalized
            self.latest_status = {
                "device_id": dto.device_id,
                "uptime_sec": dto.health.uptime_s,
                "wifi_rssi": dto.health.wifi_rssi,
                "heap_free": dto.health.free_heap,
                "status": "ONLINE",
            }
            self.latest_received_at = time.time()
            self.samples_received += 1
            self.latest_is_simulation = is_simulation

        self.telemetry_repo.save_sample(dto, run_id=None, extra={
            "pressure_bar": result["pressure"]["pressure_bar"],
            "pressure_source": result["pressure"]["source"],
            "residual": result["residual"],
            "hydraulics": result["hydraulics"],
            "ts_source": normalized["ts_source"],
            "device_ts": normalized.get("device_ts"),
        })
        self.detection_repo.save_response(response, run_id=None)

        # Log every real frame to a flat file too, independent of Mongo and
        # independent of whatever the dashboard is currently displaying — so
        # real rig data accumulates for analytics before the UI is switched
        # to live mode.
        if not is_simulation:
            log_frame(normalized, response)

    def handle_status(self, raw: dict):
        with self._lock:
            self.latest_status = dict(raw)
            self.latest_received_at = time.time()


def _on_connect(client, userdata, flags, rc):
    topic = config_loader.get("mqtt.topic", "rig/telemetry")
    status_topic = config_loader.get("mqtt.status_topic", "rig/status")
    if rc == 0:
        logger.info(f"[MQTT] Connected, subscribing to {topic} and {status_topic}")
        client.subscribe(topic)
        client.subscribe(status_topic)
    else:
        logger.error(f"[MQTT] Connection failed, rc={rc}")


def _on_message(client, userdata: LiveTelemetryIngestor, msg):
    try:
        raw = json.loads(msg.payload.decode("utf-8"))
    except Exception as e:
        logger.warning(f"[MQTT] Bad JSON payload on {msg.topic}: {e}")
        return
    status_topic = config_loader.get("mqtt.status_topic", "rig/status")
    if msg.topic == status_topic:
        userdata.handle_status(raw)
    else:
        userdata.handle_payload(raw)


def run_subscriber(ingestor: LiveTelemetryIngestor = None, blocking=True):
    ingestor = ingestor or LiveTelemetryIngestor()
    host = config_loader.get("mqtt.host", "localhost")
    port = config_loader.get("mqtt.port", 1883)

    client = mqtt.Client(userdata=ingestor)
    client.on_connect = _on_connect
    client.on_message = _on_message

    client.connect(host, port, keepalive=30)
    if blocking:
        client.loop_forever()
    else:
        client.loop_start()
    return client, ingestor


if __name__ == "__main__":
    run_subscriber()
