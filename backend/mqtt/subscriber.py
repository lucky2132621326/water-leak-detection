"""MQTT Telemetry Subscriber

Live-mode ingestion: subscribes to rig/telemetry, validates each payload,
runs it through the shared DetectionPipeline, persists telemetry + the
shaped response to MongoDB, and hands the latest response to whatever
process is asking (the FastAPI service, via `latest_response`).

Run standalone with: python -m backend.mqtt.subscriber
"""
import json
import threading
import paho.mqtt.client as mqtt

from backend.config.config_loader import config_loader
from backend.validators.telemetry_validator import TelemetryValidator
from backend.models.telemetry import TelemetryDTO
from backend.repositories.telemetry_repository import TelemetryRepository
from backend.repositories.detection_repository import DetectionRepository
from backend.pipeline import DetectionPipeline
from backend.response.response_builder import build_response
from backend.alerts.alert_service import get_alert_service
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
        self._lock = threading.Lock()

    def handle_payload(self, raw: dict):
        is_valid, msg = TelemetryValidator.validate(raw)
        if not is_valid:
            logger.warning(f"[MQTT] Rejected telemetry: {msg}")
            return

        dto = TelemetryDTO.from_dict(raw)
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
            self.latest_telemetry = raw

        self.telemetry_repo.save_sample(dto, run_id=None, extra={"pressure_bar": result["pressure"]["pressure_bar"]})
        self.detection_repo.save_response(response, run_id=None)
        # Roll this sample into the operator-facing incident list (Alert Center).
        get_alert_service().ingest(response, source="live", run_id=None)


def _on_connect(client, userdata, flags, rc):
    topic = config_loader.get("mqtt.topic", "rig/telemetry")
    if rc == 0:
        logger.info(f"[MQTT] Connected, subscribing to {topic}")
        client.subscribe(topic)
    else:
        logger.error(f"[MQTT] Connection failed, rc={rc}")


def _on_message(client, userdata: LiveTelemetryIngestor, msg):
    try:
        raw = json.loads(msg.payload.decode("utf-8"))
    except Exception as e:
        logger.warning(f"[MQTT] Bad JSON payload on {msg.topic}: {e}")
        return
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
