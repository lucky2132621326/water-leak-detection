"""Telemetry Ingestor — the one code path both operating modes run through.

This replaces the previous pair of near-duplicate implementations
(`LiveTelemetryIngestor.handle_payload` and `ReplayPlayer._play`), which had
silently drifted apart in eight ways: replay skipped validation entirely,
bypassed the typed DTO, persisted neither telemetry nor detections, and computed
`leak_active` from the detector's own output while live computed it from ground
truth.

Consolidating them means a mock sample and a rig sample are indistinguishable
to everything downstream — same validator, same DTO, same detectors, same
response shape, same persistence.
"""
import threading
import time

from backend.alerts.alert_service import get_alert_service
from backend.detectors.residual import compute_residual
from backend.models.telemetry import TelemetryDTO
from backend.pipeline import DetectionPipeline
from backend.repositories.detection_repository import DetectionRepository, LeakEventRepository
from backend.repositories.telemetry_repository import TelemetryRepository
from backend.response.response_builder import build_response
from backend.services.experiment_service import get_experiment_service
from backend.validators.telemetry_validator import TelemetryValidator
from backend.utils.logger import logger

HISTORY_LIMIT = 120

#: Floor for a believable Unix timestamp (2023-11-14). This is deliberately the
#: same constant the firmware tests against in main.cpp, because it is the same
#: judgement: below this, the value is not an epoch.
MIN_PLAUSIBLE_TS = 1_700_000_000
#: Ceiling, as a tolerance ahead of the server clock. Catches a rig whose RTC
#: has run away, without rejecting ordinary clock skew.
MAX_TS_SKEW_SEC = 86_400


def repair_timestamp(raw: dict) -> tuple[float, bool]:
    """Return `(ts, was_substituted)` for one payload.

    The ESP32 falls back to `millis()/1000` — uptime in seconds — whenever NTP
    has not yet synced:

        time_t epoch = time(nullptr);
        unsigned long ts = (epoch > 1700000000) ? epoch : (now / 1000);

    That is a different epoch in the same field, and nothing downstream could
    tell. Stored samples land in 1970, alert start times and detection latencies
    are computed against a bogus origin, and MNF — the one detector whose
    verdict depends on the wall clock — reads the hour from it. A rig up for
    ~20 hours without NTP publishes uptimes that map into the 01:00–05:00 night
    window, switching MNF on for a rig that is not at night at all.

    Substituting server receive time is better than rejecting the packet: the
    flow data is perfectly good, only its clock is wrong, and the server's own
    clock is the best available estimate of when the sample arrived.
    """
    raw_ts = raw.get("ts")
    now = time.time()
    try:
        ts = float(raw_ts)
    except (TypeError, ValueError):
        return now, True
    if ts < MIN_PLAUSIBLE_TS or ts > now + MAX_TS_SKEW_SEC:
        return now, True
    return ts, False


def flatten_sample(raw: dict, response: dict = None, leak_active: bool = False) -> dict:
    """Normalise a wire-format payload into the flat shape the dashboard charts.

    There is deliberately no per-mode branch here — mock and live must flatten
    identically or the dashboard is showing two different things under one label.

    `leak_active` is GROUND TRUTH: whether a physical leak window is open right
    now, according to the operator-logged `leak_events` record. It is never the
    detector's opinion, so the dashboard can honestly show "the detector says
    clear while a clamp is actually open".
    """
    if raw is None:
        return None

    flow = raw.get("flow") or {}
    power = raw.get("power") or {}
    vib = raw.get("vibration") or {}
    act = raw.get("actuators") or {}

    q_in = float(flow.get("q_in_lpm", 0.0) or 0.0)
    q_out = float(flow.get("q_out_lpm", 0.0) or 0.0)
    q_branch = float(flow.get("q_branch_lpm", 0.0) or 0.0)

    return {
        "ts": raw.get("ts"),
        "q_in": q_in,
        "q_out": q_out,
        "q_branch": q_branch,
        "current_ma": float(power.get("current_ma", 0.0) or 0.0),
        "bus_v": float(power.get("bus_v", 0.0) or 0.0),
        # Topology-aware — never recomputed here with a different formula than
        # the detectors used, which is how the two once drifted apart.
        "residual": (response or {}).get("residual", round(compute_residual(q_in, q_out, q_branch), 3)),
        "band_mid": vib.get("band_mid"),
        "vib_rms": vib.get("rms"),
        "piezo_rms": vib.get("piezo_rms"),
        "water_c": (raw.get("temp") or {}).get("water_c"),
        "leak_active": bool(leak_active),
        "pump_on": bool(act.get("pump1", False)),
        "pump2_on": bool(act.get("pump2", False)),
        "servo_deg": int(act.get("servo_deg", 0) or 0),
    }


class TelemetryIngestor:
    """Owns pipeline state and the latest evaluated response for one mode."""

    def __init__(self, source_name: str = "live", persist: bool = True,
                 telemetry_repo=None, detection_repo=None, alert_service=None):
        self.source_name = source_name
        self.persist = persist
        self._telemetry_repo = telemetry_repo
        self._detection_repo = detection_repo
        self._alert_service = alert_service

        self.pipeline = DetectionPipeline()
        self.latest_response = None
        self.latest_telemetry = None
        self.latest_flat = None
        self.history = []
        self.rejected_count = 0
        self.sample_count = 0
        #: Samples whose clock had to be replaced. A non-zero count on a live rig
        #: means NTP has not synced — worth surfacing, not worth dropping data for.
        self.clock_substituted_count = 0
        self._seq = 0
        #: Cached open ground-truth windows for the current run.
        self._gt_run_id = object()   # sentinel: never equal to a real run_id
        self._gt_windows = []
        self._leak_event_repo = None
        self._lock = threading.RLock()

    # --- lazily-resolved collaborators (so importing needs no MongoDB) ----
    @property
    def telemetry_repo(self):
        if self._telemetry_repo is None:
            self._telemetry_repo = TelemetryRepository()
        return self._telemetry_repo

    @property
    def leak_event_repo(self):
        if self._leak_event_repo is None:
            self._leak_event_repo = LeakEventRepository()
        return self._leak_event_repo

    @property
    def detection_repo(self):
        if self._detection_repo is None:
            self._detection_repo = DetectionRepository()
        return self._detection_repo

    @property
    def alerts(self):
        return self._alert_service or get_alert_service()

    # --- lifecycle --------------------------------------------------------
    def reset(self):
        """Discard all detector state.

        Every detector is stateful — mass balance keeps a rolling window, CUSUM
        an accumulator, MNF and the acoustic channel their own baselines. Without
        this, switching from a live rig into a mock scenario would evaluate the
        first synthetic samples against the rig's learned baseline and produce
        nonsense. Called on every mode switch.
        """
        with self._lock:
            self.pipeline = DetectionPipeline()
            self._gt_run_id = object()
            self._gt_windows = []
            self.latest_response = None
            self.latest_telemetry = None
            self.latest_flat = None
            self.history = []
            self.rejected_count = 0
            self.sample_count = 0
            self.clock_substituted_count = 0
            self._seq = 0
        logger.info(f"[Ingestor:{self.source_name}] detector state reset")

    # --- the shared path --------------------------------------------------
    def ingest(self, raw: dict, run_id: str = None):
        """Evaluate one wire-format sample. Returns the shaped response, or None
        if the payload was rejected."""
        is_valid, message = TelemetryValidator.validate(raw)
        if not is_valid:
            self.rejected_count += 1
            logger.warning(f"[Ingestor:{self.source_name}] rejected telemetry: {message}")
            return None

        dto = TelemetryDTO.from_dict(raw)

        # Repair an unsynced rig clock before anything reads it. Done here rather
        # than in the validator because the sample is good — only its clock is
        # wrong — and rejecting it would discard usable flow data.
        ts, substituted = repair_timestamp(raw)
        if substituted:
            original_ts = raw.get("ts")
            self.clock_substituted_count += 1
            dto.ts = ts
            raw = {**raw, "ts": ts}
            if self.clock_substituted_count == 1:
                # Once per session, not once per sample — an unsynced rig would
                # otherwise emit this at 1 Hz forever.
                logger.warning(
                    f"[Ingestor:{self.source_name}] implausible ts {original_ts!r} "
                    f"— substituting server time. On a rig this means NTP has not "
                    f"synced and the ESP32 is publishing uptime instead of an epoch."
                )

        if not raw.get("seq"):
            # Neither the ESP32 nor the mock generator numbers its samples;
            # assigning here keeps stored records individually addressable and
            # makes gaps detectable within a session.
            self._seq += 1
            dto.seq = self._seq

        # P1 is the supply pump. P2 only generates demand, so it says nothing
        # about whether the loop is pressurised and flowing.
        pump_on = dto.actuators.pump1
        result = self.pipeline.process_sample(
            ts=dto.ts,
            q_in=dto.flow.q_in_lpm,
            q_out=dto.flow.q_out_lpm,
            q_branch=dto.flow.q_branch_lpm,
            current_ma=dto.power.current_ma,
            bus_v=dto.power.bus_v,
            pump_on=pump_on,
            servo_state_deg=dto.actuators.servo_deg,
            vibration=dto.vibration,
            water_c=dto.temp.water_c,
        )
        response = build_response(result)

        # An explicit run_id wins (mock scenario runs); otherwise fall back to
        # whatever experiment the operator has recording.
        effective_run_id = run_id if run_id is not None else get_experiment_service().active_run_id()

        # Ground truth for the dashboard's "detector says X, reality is Y" strip:
        # is a physically-logged leak window open at this instant? Never the
        # detector's own output.
        leak_active = self._leak_window_open(dto.ts, effective_run_id)

        with self._lock:
            self.latest_response = response
            self.latest_telemetry = raw
            self.latest_flat = flatten_sample(raw, response, leak_active=leak_active)
            self.history.append(self.latest_flat)
            if len(self.history) > HISTORY_LIMIT:
                self.history.pop(0)
            self.sample_count += 1

        if self.persist:
            self.telemetry_repo.save_sample(
                dto, run_id=effective_run_id,
                extra={"source": self.source_name},
            )
            self.detection_repo.save_response(response, run_id=effective_run_id)

        self.alerts.ingest(response, source=self.source_name, run_id=effective_run_id)
        return response

    def _leak_window_open(self, ts: float, run_id: str) -> bool:
        """Is an operator-logged leak window open at `ts`?

        Cached per run and refreshed cheaply: this runs at 1 Hz and must not put
        a database round-trip in the ingest path. A missing database degrades to
        False rather than raising — an unknown ground truth must not stop
        detection.
        """
        if not self.persist:
            return False
        try:
            if run_id != self._gt_run_id:
                self._gt_run_id = run_id
                self._gt_windows = self.leak_event_repo.open_events(run_id=run_id)
            return any(w.get("open_ts", 0) <= ts and w.get("close_ts") is None
                       for w in self._gt_windows)
        except Exception:
            return False

    # --- read model -------------------------------------------------------
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "latest": self.latest_flat,
                "evaluation": self.latest_response,
                "sample_count": self.sample_count,
                "rejected_count": self.rejected_count,
                "clock_substituted_count": self.clock_substituted_count,
            }

    def recent_history(self):
        with self._lock:
            return list(self.history)
