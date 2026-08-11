"""Experiment Service — digital ground-truth logging for rig experiments.

Replaces the previous in-memory-only version, which recorded nothing: a run
existed as a dict until the process restarted, and no route could reach it, so
the "Start Ground Truth Leak Event" button had nothing to call.

Two things make a live rig session scoreable, and both happen here:

  1. **Run grouping.** While a run is active, `active_run_id` is stamped onto
     every live telemetry sample (backend/ingestion/ingestor.py reads it), so the
     samples can later be selected as a set. Live telemetry outside a run keeps
     `run_id = None` and is treated as free-running monitoring.

  2. **Ground truth.** Operator start/stop actions are written to `leak_events`
     with machine timestamps at the moment of the action — which is what makes
     detection latency a measurement rather than a recollection.
"""
import threading
import time

from backend.repositories.db import get_db
from backend.repositories.detection_repository import LeakEventRepository
from backend.utils.logger import logger


class ExperimentService:
    def __init__(self, db=None):
        self._lock = threading.RLock()
        self._db = db
        self.active_experiment = None
        self.active_leak_event = None

    def _database(self):
        if self._db is None:
            self._db = get_db()
        return self._db

    # --- run lifecycle ---------------------------------------------------
    def active_run_id(self):
        """Read by the live ingestor on every sample — keep it cheap."""
        exp = self.active_experiment
        return exp["run_id"] if exp else None

    def start_run(self, run_id: str = None, operator: str = "unknown",
                  location: str = "Branch_A", leak_size_lpm: float = 0.0,
                  pump_mode: str = "Constant 12V", notes: str = ""):
        with self._lock:
            if self.active_experiment:
                return {"error": f"Run '{self.active_experiment['run_id']}' is already active. Stop it first."}

            run_id = run_id or f"RUN_{time.strftime('%Y%m%d_%H%M%S')}"
            db = self._database()
            if db.experiment_runs.find_one({"run_id": run_id}):
                return {"error": f"Run '{run_id}' already exists. Choose another id."}

            doc = {
                "run_id": run_id,
                "operator": operator,
                "date": time.strftime("%Y-%m-%d"),
                "location": location,
                "leak_size_lpm": float(leak_size_lpm),
                "pump_mode": pump_mode,
                "notes": notes,
                "start_ts": time.time(),
                "stop_ts": None,
                "duration_sec": None,
                "status": "RUNNING",
                "source": "live",
            }
            db.experiment_runs.insert_one(dict(doc))
            self.active_experiment = doc
            self.active_leak_event = None
            logger.info(f"[Experiment] Started run {run_id} ({location}, target {leak_size_lpm} L/min)")
            return doc

    def stop_run(self):
        with self._lock:
            if not self.active_experiment:
                return {"error": "No run is active."}

            # An operator who forgets to close a leak event shouldn't leave
            # dangling ground truth — close it at the run boundary.
            if self.active_leak_event and self.active_leak_event.get("is_active"):
                self.stop_ground_truth_leak(_locked=True)

            exp = self.active_experiment
            stop_ts = time.time()
            exp.update({
                "stop_ts": stop_ts,
                "duration_sec": round(stop_ts - exp["start_ts"], 1),
                "status": "COMPLETED",
            })
            self._database().experiment_runs.update_one(
                {"run_id": exp["run_id"]},
                {"$set": {"stop_ts": exp["stop_ts"], "duration_sec": exp["duration_sec"], "status": "COMPLETED"}},
            )
            self.active_experiment = None
            logger.info(f"[Experiment] Completed run {exp['run_id']} after {exp['duration_sec']}s")
            return exp

    # --- ground truth ----------------------------------------------------
    def start_ground_truth_leak(self, location: str = None, severity_lpm: float = None, notes: str = ""):
        with self._lock:
            if not self.active_experiment:
                return {"error": "Start a run before logging ground truth."}
            if self.active_leak_event and self.active_leak_event.get("is_active"):
                return {"error": "A ground-truth leak event is already open."}

            exp = self.active_experiment
            event = LeakEventRepository(self._database()).create_event(
                start_ts=time.time(),
                location_node=location or exp["location"],
                severity_lpm=float(severity_lpm if severity_lpm is not None else exp["leak_size_lpm"]),
                run_id=exp["run_id"],
                is_ground_truth=True,
                notes=notes or "Operator-logged leak injection",
            )
            event["_id"] = str(event["_id"])
            event["is_active"] = True
            self.active_leak_event = event
            logger.info(f"[GroundTruth] Leak OPENED at {event['start_ts']:.0f} on {event['location_node']}")
            return event

    def stop_ground_truth_leak(self, _locked: bool = False):
        def _do():
            if not self.active_leak_event or not self.active_leak_event.get("is_active"):
                return {"error": "No open ground-truth leak event."}
            stop_ts = time.time()
            db = self._database()
            db.leak_events.update_one(
                {"run_id": self.active_leak_event["run_id"], "stop_ts": None},
                {"$set": {"stop_ts": stop_ts}},
            )
            self.active_leak_event.update({
                "stop_ts": stop_ts,
                "is_active": False,
                "duration_sec": round(stop_ts - self.active_leak_event["start_ts"], 1),
            })
            logger.info(f"[GroundTruth] Leak CLOSED after {self.active_leak_event['duration_sec']}s")
            return self.active_leak_event

        if _locked:
            return _do()
        with self._lock:
            return _do()

    # --- read model -------------------------------------------------------
    def status(self):
        exp = self.active_experiment
        leak = self.active_leak_event
        now = time.time()
        return {
            "run_active": exp is not None,
            "run": ({**exp, "elapsed_sec": round(now - exp["start_ts"], 1)} if exp else None),
            "leak_open": bool(leak and leak.get("is_active")),
            "leak_event": ({**leak, "elapsed_sec": round(now - leak["start_ts"], 1)} if leak else None),
            "ground_truth_events": self.events_for_active_run(),
        }

    def events_for_active_run(self):
        if not self.active_experiment:
            return []
        events = list(self._database().leak_events.find(
            {"run_id": self.active_experiment["run_id"]}, {"_id": 0}
        ).sort("start_ts", 1))
        return events


_default_experiment_service = None


def get_experiment_service() -> ExperimentService:
    global _default_experiment_service
    if _default_experiment_service is None:
        _default_experiment_service = ExperimentService()
    return _default_experiment_service
