"""Non-blocking Twilio WhatsApp notifications for newly-created leak alerts.

Credentials are read only from environment variables. Detection never waits
for or depends on Twilio: delivery runs on a single background worker and all
network/configuration errors are logged without escaping into the pipeline.
"""
from __future__ import annotations

import base64
import json
import os
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from backend.utils.logger import logger


IST = timezone(timedelta(hours=5, minutes=30), "IST")
# Matches the ingestion clock-integrity floor. Values below this are ESP32
# uptime/test offsets, not Unix wall-clock timestamps, and would render as 1970.
MIN_PLAUSIBLE_EVENT_TS = 1_700_000_000
MAX_FUTURE_SKEW_SEC = 86_400
DEFAULT_ALERT_ACTION = "Inspect the pipeline and verify in the field."
INCIDENT_TEMPLATE_BODY = (
    "🚨 LEAK DETECTED\n"
    "Location: {{1}}\n"
    "Estimated leak rate: {{2}} L/min\n"
    "Confidence: {{3}} ({{4}}%)\n"
    "Detected: {{5}}\n"
    "Action: {{6}}"
)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class WhatsAppNotifier:
    def __init__(self, account_sid: str = "", auth_token: str = "", from_number: str = "",
                 to_number: str = "", content_sid: str = "", enabled: bool = False,
                 notify_mock: bool = False, notify_replay: bool | None = None,
                 timeout_sec: float = 8.0,
                 action_text: str = DEFAULT_ALERT_ACTION,
                 transport=None, executor=None):
        self.account_sid = account_sid.strip()
        self.auth_token = auth_token.strip()
        self.from_number = self._whatsapp_number(from_number)
        self.to_number = self._whatsapp_number(to_number)
        self.content_sid = content_sid.strip()
        self.enabled = bool(enabled)
        # ``notify_replay`` is a migration alias from the retired third mode.
        self.notify_mock = bool(notify_mock if notify_replay is None else notify_replay)
        self.timeout_sec = float(timeout_sec)
        self.action_text = action_text.strip() or DEFAULT_ALERT_ACTION
        self._transport = transport or self._post
        self._executor = executor or ThreadPoolExecutor(max_workers=1, thread_name_prefix="whatsapp")
        self._lock = threading.Lock()
        self._queued_alert_ids: set[str] = set()

    @staticmethod
    def _whatsapp_number(value: str) -> str:
        value = (value or "").strip()
        if value and not value.startswith("whatsapp:"):
            return f"whatsapp:{value}"
        return value

    @classmethod
    def from_env(cls):
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass

        enabled = _as_bool(os.getenv("TWILIO_WHATSAPP_ENABLED"), False)
        notifier = cls(
            account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
            auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
            from_number=os.getenv("TWILIO_WHATSAPP_FROM", ""),
            to_number=os.getenv("TWILIO_WHATSAPP_TO", ""),
            content_sid=os.getenv("TWILIO_CONTENT_SID", ""),
            enabled=enabled,
            notify_mock=_as_bool(
                os.getenv("TWILIO_NOTIFY_MOCK", os.getenv("TWILIO_NOTIFY_REPLAY")), False
            ),
            timeout_sec=float(os.getenv("TWILIO_TIMEOUT_SEC", "8")),
            action_text=os.getenv("TWILIO_ALERT_ACTION", DEFAULT_ALERT_ACTION),
        )
        if enabled:
            missing = notifier.missing_configuration()
            if missing:
                logger.error(f"[WhatsApp] Disabled: missing environment variables: {', '.join(missing)}")
                notifier.enabled = False
            else:
                logger.info("[WhatsApp] Twilio leak notifications enabled")
        return notifier

    def missing_configuration(self) -> list[str]:
        values = {
            "TWILIO_ACCOUNT_SID": self.account_sid,
            "TWILIO_AUTH_TOKEN": self.auth_token,
            "TWILIO_WHATSAPP_FROM": self.from_number,
            "TWILIO_WHATSAPP_TO": self.to_number,
            "TWILIO_CONTENT_SID": self.content_sid,
        }
        return [name for name, value in values.items() if not value]

    def enqueue(self, alert: dict) -> bool:
        """Queue one notification per alert ID and return whether it was queued."""
        if not self.enabled:
            return False
        # Only physical incidents notify by default. Mock scenarios must never
        # page an operator unless explicitly opted in.
        if alert.get("source") != "live" and not self.notify_mock:
            return False
        alert_id = str(alert.get("alert_id") or "")
        if not alert_id:
            return False
        with self._lock:
            if alert_id in self._queued_alert_ids:
                return False
            self._queued_alert_ids.add(alert_id)
        self._executor.submit(self._deliver_safely, dict(alert))
        return True

    def _deliver_safely(self, alert: dict):
        try:
            sid = self.send(alert)
            logger.info(f"[WhatsApp] Sent {alert['alert_id']} via Twilio message {sid}")
        except Exception as exc:
            logger.warning(f"[WhatsApp] Delivery failed for {alert.get('alert_id')}: {exc}")

    def send(self, alert: dict) -> str:
        """Synchronously deliver an alert; intended for the worker and tests."""
        variables = self.template_variables(alert)
        form = {
            "From": self.from_number,
            "To": self.to_number,
            "ContentSid": self.content_sid,
            "ContentVariables": json.dumps(variables, separators=(",", ":")),
        }
        response = self._transport(form)
        sid = response.get("sid") if isinstance(response, dict) else None
        if not sid:
            raise RuntimeError("Twilio response did not contain a message SID")
        return str(sid)

    def template_variables(self, alert: dict) -> dict[str, str]:
        """Map an incident to the approved six-variable WhatsApp template."""
        now = time.time()
        try:
            event_ts = float(alert.get("start_ts"))
        except (TypeError, ValueError):
            event_ts = now
        if event_ts < MIN_PLAUSIBLE_EVENT_TS or event_ts > now + MAX_FUTURE_SKEW_SEC:
            logger.warning(
                f"[WhatsApp] Replacing implausible incident timestamp {event_ts} "
                "with current server time"
            )
            event_ts = now
        event_time = datetime.fromtimestamp(event_ts, tz=IST).strftime("%Y-%m-%d %H:%M:%S IST")
        rate = alert.get("peak_leak_rate_lpm")
        if rate is None:
            rate = alert.get("leak_rate_lpm")
        likelihood = alert.get("likelihood_score")
        return {
            "1": str(alert.get("zone") or "Unknown"),
            "2": f"{float(rate or 0.0):.3f}",
            "3": str(alert.get("confidence_tier") or "UNAVAILABLE"),
            "4": f"{float(likelihood or 0.0):.1f}",
            "5": event_time,
            "6": self.action_text,
        }

    def format_preview(self, alert: dict) -> str:
        """Render the human-readable message for tests and operator previews."""
        rendered = INCIDENT_TEMPLATE_BODY
        for key, value in self.template_variables(alert).items():
            rendered = rendered.replace("{{" + key + "}}", value)
        return rendered

    def _post(self, form: dict) -> dict:
        url = f"https://api.twilio.com/2010-04-01/Accounts/{urllib.parse.quote(self.account_sid)}/Messages.json"
        body = urllib.parse.urlencode(form).encode("utf-8")
        credentials = base64.b64encode(f"{self.account_sid}:{self.auth_token}".encode("utf-8")).decode("ascii")
        request = urllib.request.Request(
            url,
            data=body,
            headers={
                "Authorization": f"Basic {credentials}",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "water-leak-detection/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            # Twilio's response is useful for operators, but never log the
            # Authorization header or configured token.
            detail = exc.read().decode("utf-8", errors="replace")[:500]
            raise RuntimeError(f"Twilio HTTP {exc.code}: {detail}") from exc


_default_notifier = None


def get_whatsapp_notifier() -> WhatsAppNotifier:
    global _default_notifier
    if _default_notifier is None:
        _default_notifier = WhatsAppNotifier.from_env()
    return _default_notifier
