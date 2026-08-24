import json
from unittest.mock import patch

from backend.alerts.alert_service import AlertService
from backend.notifications.whatsapp import WhatsAppNotifier


class ImmediateExecutor:
    def submit(self, fn, *args, **kwargs):
        fn(*args, **kwargs)


def alert(alert_id="LEAK-0001", source="live"):
    return {
        "alert_id": alert_id, "source": source, "zone": "Main_Trunk",
        "start_ts": 1_754_885_358, "peak_leak_rate_lpm": 0.306,
        "confidence_tier": "HIGH", "likelihood_score": 38.0,
    }


def response(ts=1_754_131_200):
    return {
        "ts": ts, "residual": 1.25, "is_alarm": True,
        "likelihood_score": 82.0, "confidence_tier": "HIGH", "zone": "Branch_A",
        "evidence": "flow residual +1.25 L/min", "active_methods": ["mass_balance", "cusum"],
    }


def configured_notifier(transport, notify_mock=False):
    return WhatsAppNotifier(
        account_sid="AC_test", auth_token="secret_test_token",
        from_number="+14155238886", to_number="+919999999999",
        content_sid="HX_test", enabled=True, notify_mock=notify_mock,
        transport=transport, executor=ImmediateExecutor(),
    )


def test_twilio_template_payload_uses_complete_incident_evidence():
    calls = []
    notifier = configured_notifier(lambda form: calls.append(form) or {"sid": "SM_test"})
    assert notifier.enqueue(alert()) is True
    assert calls[0]["From"] == "whatsapp:+14155238886"
    assert calls[0]["To"] == "whatsapp:+919999999999"
    assert calls[0]["ContentSid"] == "HX_test"
    variables = json.loads(calls[0]["ContentVariables"])
    assert variables == {
        "1": "Main_Trunk",
        "2": "0.306",
        "3": "HIGH",
        "4": "38.0",
        "5": "2025-08-11 09:39:18 IST",
        "6": "Inspect the pipeline and verify in the field.",
    }


def test_operator_preview_matches_the_approved_template_layout():
    notifier = configured_notifier(lambda _form: {"sid": "SM_test"})
    preview = notifier.format_preview(alert())
    assert preview == (
        "🚨 LEAK DETECTED\n"
        "Location: Main_Trunk\n"
        "Estimated leak rate: 0.306 L/min\n"
        "Confidence: HIGH (38.0%)\n"
        "Detected: 2025-08-11 09:39:18 IST\n"
        "Action: Inspect the pipeline and verify in the field."
    )


def test_1970_device_timestamp_uses_current_ist_date():
    notifier = configured_notifier(lambda _form: {"sid": "SM_test"})
    bad_clock_alert = alert()
    bad_clock_alert["start_ts"] = 1000

    # 2026-08-12 06:32:38 UTC = 2026-08-12 12:02:38 IST.
    with patch("backend.notifications.whatsapp.time.time", return_value=1_786_516_358):
        variables = notifier.template_variables(bad_clock_alert)

    assert variables["5"] == "2026-08-12 12:02:38 IST"


def test_duplicate_alert_id_is_sent_only_once():
    calls = []
    notifier = configured_notifier(lambda form: calls.append(form) or {"sid": "SM_test"})
    assert notifier.enqueue(alert()) is True
    assert notifier.enqueue(alert()) is False
    assert len(calls) == 1


def test_mock_notifications_are_opt_in():
    calls = []
    notifier = configured_notifier(lambda form: calls.append(form) or {"sid": "SM_test"})
    assert notifier.enqueue(alert(source="mock")) is False
    assert calls == []

    opted_in = configured_notifier(lambda form: calls.append(form) or {"sid": "SM_test"}, notify_mock=True)
    assert opted_in.enqueue(alert(source="mock")) is True
    assert len(calls) == 1


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
