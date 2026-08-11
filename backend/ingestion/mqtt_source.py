"""Live Sensor Mode source — ESP32 telemetry over MQTT.

This is now a thin transport adapter. It subscribes, decodes JSON, and hands the
payload to the shared TelemetryIngestor; it performs no validation, parsing or
evaluation of its own. Everything after `ingestor.ingest(raw)` is identical to
Mock Data Mode by construction.
"""
import json
import threading

import paho.mqtt.client as mqtt

from backend.config.config_loader import config_loader
from backend.ingestion.telemetry_source import TelemetrySource
from backend.utils.logger import logger
from backend.repositories.file_logger import log_frame


class MqttTelemetrySource(TelemetrySource):
    name = "live"

    def __init__(self, host: str = None, port: int = None, topic: str = None):
        self.host = host or config_loader.get("mqtt.host", "localhost")
        self.port = int(port or config_loader.get("mqtt.port", 1883))
        self.topic = topic or config_loader.get("mqtt.topic", "rig/telemetry")
        self.status_topic = config_loader.get("mqtt.status_topic", "rig/status")
        self.username = config_loader.get("mqtt.username", "")
        self.password = config_loader.get("mqtt.password", "")
        self.client = None
        self._ingestor = None
        self._running = False
        self._lock = threading.Lock()

    @property
    def is_running(self) -> bool:
        return self._running and bool(self.client and self.client.is_connected())

    def start(self, ingestor) -> None:
        with self._lock:
            if self._running:
                return
            self._ingestor = ingestor
            self.client = mqtt.Client(userdata=self)
            if self.username:
                self.client.username_pw_set(self.username, self.password)
            self.client.on_connect = _on_connect
            self.client.on_message = _on_message
            self.client.on_disconnect = _on_disconnect
            try:
                self.client.connect(self.host, self.port, keepalive=30)
                self.client.loop_start()
                self._running = True
                logger.info(f"[LiveSource] connecting to {self.host}:{self.port}, topic {self.topic}")
            except Exception as e:
                # Not fatal: the dashboard stays usable and reports the broker as
                # unreachable rather than the whole service failing to start.
                self.client = None
                self._running = False
                logger.warning(f"[LiveSource] broker unreachable at {self.host}:{self.port}: {e}")

    def stop(self) -> None:
        with self._lock:
            if self.client:
                try:
                    self.client.loop_stop()
                    self.client.disconnect()
                except Exception as e:
                    logger.warning(f"[LiveSource] error during disconnect: {e}")
            self.client = None
            self._running = False
            logger.info("[LiveSource] stopped")

    def publish_command(self, payload: dict) -> tuple[bool, str]:
        """Send a command to the rig on `rig/cmd`. Live mode only — there is no
        hardware to actuate in Mock Data Mode."""
        if not self.is_running:
            return False, "MQTT broker unreachable — cannot reach the rig."
        cmd_topic = config_loader.get("mqtt.cmd_topic", "rig/cmd")
        try:
            info = self.client.publish(cmd_topic, json.dumps(payload), qos=1)
            info.wait_for_publish(timeout=2)
            logger.info(f"[LiveSource] published to {cmd_topic}: {payload}")
            return True, f"Command published to {cmd_topic}"
        except Exception as e:
            return False, f"Publish failed: {e}"

    def describe(self) -> dict:
        return {
            "source": self.name,
            "running": self.is_running,
            "broker": f"{self.host}:{self.port}",
            "topic": self.topic,
        }


def _on_connect(client, userdata: MqttTelemetrySource, flags, rc):
    if rc == 0:
        logger.info(f"[LiveSource] connected, subscribing to {userdata.topic}")
        client.subscribe(userdata.topic)
        client.subscribe(userdata.status_topic)
    else:
        logger.error(f"[LiveSource] connection failed, rc={rc}")


def _on_disconnect(client, userdata: MqttTelemetrySource, rc):
    if rc != 0:
        logger.warning(f"[LiveSource] unexpected disconnect (rc={rc}); paho will retry")


def _on_message(client, userdata: MqttTelemetrySource, msg):
    try:
        raw = json.loads(msg.payload.decode("utf-8"))
    except Exception as e:
        logger.warning(f"[LiveSource] bad JSON on {msg.topic}: {e}")
        return
    if msg.topic == userdata.status_topic:
        userdata._ingestor.update_device_status(raw) if userdata._ingestor is not None else None
        return
    if userdata._ingestor is not None:
        response = userdata._ingestor.ingest(raw)
        if response is not None:
            log_frame(raw, response)
