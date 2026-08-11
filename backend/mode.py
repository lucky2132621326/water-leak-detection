"""Operating mode — the process-wide switch that decides which data store is live.

There are exactly two modes and they must never see each other's data. A mock
scenario is synthetic; a live run is physical evidence from the rig. Mixing them
destroys the credibility of every metric derived from hardware, because nobody
can tell afterwards which events were real.

This module is the single source of truth for "which mode are we in". Three
things key off it:

  * `backend/repositories/db.py`   — routes to a different MongoDB database
  * `backend/alerts/alert_service.py` — one service instance per mode
  * every stored document          — carries a `mode` field of its own

The database split is the real barrier; the per-document `mode` field is
deliberate redundancy. If a collection is ever dumped, copied between
environments, or inspected by hand, each record still states what it is rather
than relying on which file it happened to be sitting in.
"""
import threading

MODE_LIVE = "live"
MODE_MOCK = "mock"
MODES = (MODE_LIVE, MODE_MOCK)

#: Start in mock. A dashboard with no rig attached should be useful immediately,
#: and mock is the mode where that is honest.
_active_mode = MODE_MOCK
_lock = threading.RLock()


def get_active_mode() -> str:
    with _lock:
        return _active_mode


def set_active_mode(mode: str) -> str:
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r} — expected one of {MODES}")
    global _active_mode
    with _lock:
        _active_mode = mode
    return mode


def require_mode(mode: str) -> str:
    """Validate a mode supplied by a caller (API parameter, stored document)."""
    if mode not in MODES:
        raise ValueError(f"unknown mode {mode!r} — expected one of {MODES}")
    return mode


def is_live(mode: str = None) -> bool:
    return (mode or get_active_mode()) == MODE_LIVE
