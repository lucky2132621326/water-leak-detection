"""Derived water-flow state for dashboard consumers.

The ESP32 reports measured rates; this module only answers whether those rates
constitute water movement and whether the answer is still fresh. Keeping the
decision in the backend ensures every frontend sees the same state.
"""
from __future__ import annotations

import time
from typing import Optional


# Any strictly positive rate is meaningful to the display. Hardware resolution
# and detector thresholds are separate concerns; the UI must not hide a valid
# 0.01 L/min sample merely because it is too small to alarm.
FLOWING_THRESHOLD_LPM = 0.0
FLOW_STALE_AFTER_SECONDS = 15.0
FLOW_DISPLAY_HOLD_SECONDS = 10.0

_CHANNELS = (
    ("flow_1", "q_in", "Qin"),
    ("flow_2", "q_out", "Qout"),
    ("flow_3", "q_branch", "Qbranch"),
)


def derive_water_flow_state(
    latest: Optional[dict],
    received_at: Optional[float],
    *,
    history: Optional[list[dict]] = None,
    now: Optional[float] = None,
    threshold_lpm: float = FLOWING_THRESHOLD_LPM,
    stale_after_seconds: float = FLOW_STALE_AFTER_SECONDS,
    hold_seconds: float = FLOW_DISPLAY_HOLD_SECONDS,
) -> dict:
    """Return one honest, UI-ready view of the three flow channels."""
    if latest is None or received_at is None:
        return {
            "status": "waiting",
            "has_sample": False,
            "is_flowing": None,
            "last_known_flowing": None,
            "sample_age_s": None,
            "threshold_lpm": threshold_lpm,
            "display_hold_seconds": hold_seconds,
            "sensors": {
                key: {"label": label, "rate_lpm": None, "flowing": None}
                for key, _field, label in _CHANNELS
            },
        }

    now = time.time() if now is None else now
    age = max(0.0, now - float(received_at))
    history = list(history or [])
    # The latest item may not yet be visible in a separately-read history
    # snapshot. Include it explicitly with the authoritative receive time.
    samples = [*history, {**latest, "received_at": received_at}]
    sensors = {}
    for key, field, label in _CHANNELS:
        raw_rate = latest.get(field)
        try:
            rate = max(0.0, float(raw_rate))
        except (TypeError, ValueError):
            rate = 0.0
        last_nonzero_rate = None
        last_nonzero_at = None
        for sample in reversed(samples):
            try:
                candidate_rate = max(0.0, float(sample.get(field)))
                candidate_at = float(sample.get("received_at", sample.get("ts")))
            except (TypeError, ValueError):
                continue
            if candidate_rate > threshold_lpm:
                last_nonzero_rate = candidate_rate
                last_nonzero_at = candidate_at
                break

        hold_remaining = (
            max(0.0, hold_seconds - (now - last_nonzero_at))
            if last_nonzero_at is not None else 0.0
        )
        display_rate = last_nonzero_rate if hold_remaining > 0 else 0.0
        sensors[key] = {
            "label": label,
            "raw_rate_lpm": round(rate, 3),
            "rate_lpm": round(display_rate, 3),
            "flowing": display_rate > threshold_lpm,
            "held": display_rate > threshold_lpm and rate <= threshold_lpm,
            "hold_remaining_s": round(hold_remaining, 2),
        }

    last_known_flowing = any(sensor["flowing"] for sensor in sensors.values())
    stale = age > stale_after_seconds
    return {
        "status": "stale" if stale else ("flowing" if last_known_flowing else "no_flow"),
        "has_sample": True,
        # A stale reading describes the past, not whether water is moving now.
        "is_flowing": None if stale else last_known_flowing,
        "last_known_flowing": last_known_flowing,
        "sample_age_s": round(age, 2),
        "threshold_lpm": threshold_lpm,
        "display_hold_seconds": hold_seconds,
        "sensors": sensors,
    }
