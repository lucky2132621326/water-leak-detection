import json

from backend.alerts.alert_service import AlertService
from backend.notifications.whatsapp import WhatsAppNotifier


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


def alert(alert_id="LEAK-0001", source="live"):
    return {"alert_id": alert_id, "source": source, "zone": "Branch_A", "start_ts": 1_754_131_200}


def response(ts=1_754_131_200):
    return {
        "ts": ts, "residual": 1.25, "is_alarm": True,
        "likelihood_score": 82.0, "confidence_tier": "HIGH", "zone": "Branch_A",
        "evidence": "flow residual +1.25 L/min", "active_methods": ["mass_balance", "cusum"],
    }


def configured_notifier(transport, notify_replay=False):
    return WhatsAppNotifier(
        account_sid="AC_test", auth_token="secret_test_token",
        from_number="+14155238886", to_number="+919999999999",
        content_sid="HX_test", enabled=True, notify_replay=notify_replay,
        transport=transport, executor=ImmediateExecutor(),
    )


def test_twilio_template_payload_uses_zone_and_event_time():
    calls = []
    notifier = configured_notifier(lambda form: calls.append(form) or {"sid": "SM_test"})
    assert notifier.enqueue(alert()) is True
    assert calls[0]["From"] == "whatsapp:+14155238886"
    assert calls[0]["To"] == "whatsapp:+919999999999"
    assert calls[0]["ContentSid"] == "HX_test"
    variables = json.loads(calls[0]["ContentVariables"])
    assert variables["1"] == "Branch_A"
    assert "2025" in variables["2"]


def test_duplicate_alert_id_is_sent_only_once():
    calls = []
    notifier = configured_notifier(lambda form: calls.append(form) or {"sid": "SM_test"})
    assert notifier.enqueue(alert()) is True
    assert notifier.enqueue(alert()) is False
    assert len(calls) == 1


def test_replay_notifications_are_opt_in():
    calls = []
    notifier = configured_notifier(lambda form: calls.append(form) or {"sid": "SM_test"})
    assert notifier.enqueue(alert(source="replay")) is False
    assert calls == []


def test_alert_service_queues_only_on_incident_creation():
    class Recorder:
        def __init__(self):
            self.alerts = []
        def enqueue(self, item):
            self.alerts.append(dict(item))
            return True

    recorder = Recorder()
    service = AlertService(enable_persistence=False, notifier=recorder)
    for ts in (1_754_131_200, 1_754_131_201, 1_754_131_202):
        service.ingest(response(ts), source="live")
    assert len(recorder.alerts) == 1
    assert recorder.alerts[0]["alert_id"] == "LEAK-0001"


def test_delivery_failure_never_escapes_ingestion():
    def failing_transport(_form):
        raise RuntimeError("simulated Twilio outage")

    notifier = configured_notifier(failing_transport)
    service = AlertService(enable_persistence=False, notifier=notifier)
    created = service.ingest(response(), source="live")
    assert created["alert_id"] == "LEAK-0001"
    assert service.counts()["total"] == 1
