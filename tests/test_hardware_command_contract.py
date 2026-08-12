"""The API must publish only commands implemented by the ESP32 firmware."""
from backend import api_server
from backend.mode import MODE_LIVE


def test_live_pump_command_matches_firmware_fields(monkeypatch):
    published = []
    monkeypatch.setattr(api_server, "_mode", MODE_LIVE)
    monkeypatch.setattr(
        api_server,
        "_publish_command",
        lambda payload: (published.append(payload) or True, "published"),
    )

    result = api_server.leak_toggle({"pump_state": True})

    assert result["success"] is True
    assert published == [{"pump1": True}]


def test_live_leak_injection_is_not_published(monkeypatch):
    published = []
    monkeypatch.setattr(api_server, "_mode", MODE_LIVE)
    monkeypatch.setattr(
        api_server,
        "_publish_command",
        lambda payload: (published.append(payload) or True, "published"),
    )

    result = api_server.leak_toggle({"action": "OPEN", "size": 1.25})

    assert result["success"] is False
    assert "physical clamp" in result["error"]
    assert published == []


def test_air_bubble_command_is_rejected(monkeypatch):
    monkeypatch.setattr(api_server, "_mode", MODE_LIVE)

    result = api_server.leak_toggle({"air_bubbles": True})

    assert result["success"] is False
    assert "no air-bubble actuator" in result["error"]
