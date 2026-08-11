"""Live Telemetry File Logger

Appends every real telemetry frame received from the rig (and its detection
result) to a local JSONL file, independent of MongoDB and independent of
whichever mode the dashboard is currently displaying (live or replay).

This exists so real rig data accumulates for analytics as soon as hardware
starts publishing, even while the UI keeps showing mock/replay data by
default — the interface isn't switched to "live" until that's explicitly
requested via the mode toggle.

One line per frame (JSON Lines) so partial writes/crashes never corrupt
already-logged data, and the file can be tailed or streamed incrementally.
"""
import json
import os
import threading
from typing import Optional

from backend.utils.logger import logger

_LOG_PATH = os.getenv("LIVE_TELEMETRY_LOG_PATH", "data/live_telemetry.jsonl")
_lock = threading.Lock()
_frames_logged = 0


def log_frame(raw_telemetry: dict, response: Optional[dict]) -> None:
    global _frames_logged
    record = {
        "logged_at": raw_telemetry.get("ts"),
        "telemetry": raw_telemetry,
        "evaluation": response,
    }
    try:
        os.makedirs(os.path.dirname(_LOG_PATH) or ".", exist_ok=True)
        with _lock:
            with open(_LOG_PATH, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, default=str) + "\n")
            _frames_logged += 1
    except Exception as e:
        # Never let file logging take down live ingestion.
        logger.warning(f"[FileLogger] Failed to write frame to {_LOG_PATH}: {e}")


def frames_logged() -> int:
    return _frames_logged


def log_path() -> str:
    return _LOG_PATH
