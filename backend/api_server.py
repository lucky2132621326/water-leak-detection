"""FastAPI Bridge

Serves the data/detection routes server.ts used to mock. Owns the live/replay
mode toggle: both sources run every sample through the same DetectionPipeline
(backend/pipeline.py) and response_builder, so switching modes only changes
where samples come from, never how they're evaluated.

Run with: uvicorn backend.api_server:app --host 0.0.0.0 --port 8001
(8001, not 8000 — another unrelated app already occupies 8000 on the dev machine)
"""
import os
import threading
import time
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend.mqtt.subscriber import LiveTelemetryIngestor, run_subscriber
from backend.models.telemetry import TelemetryDTO
from backend.pipeline import DetectionPipeline
from backend.response.response_builder import build_response
from backend.repositories.telemetry_repository import TelemetryRepository
from backend.repositories.detection_repository import LeakEventRepository, WorkOrderRepository
from backend.repositories.db import get_db
from backend.repositories.file_logger import log_path as file_log_path, frames_logged as file_frames_logged
from backend.replay.replay_runner import ReplayRunner
from backend.scheduler.cp_sat_scheduler import CPSatWorkOrderScheduler
from backend.calibration.calibration_repository import CalibrationRepository
from backend.localization.localization_service import LocalizationService
from backend.utils.logger import logger
from backend.config.config_loader import config_loader

app = FastAPI(title="Water Leak Detection API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class ReplayPlayer:
    """Streams a stored run's telemetry through the pipeline at ~1 sample/sec,
    mirroring how live telemetry arrives, so /api/telemetry looks the same to
    the dashboard regardless of which mode is active."""

    def __init__(self):
        self.telemetry_repo = TelemetryRepository()
        self.pipeline: Optional[DetectionPipeline] = None
        self.thread: Optional[threading.Thread] = None
        self.stop_flag = threading.Event()
        self.latest_response = None
        self.latest_telemetry = None
        self.history = []
        self.current_run_id = None

    def start(self, run_id: str, speed: float = 4.0):
        self.stop()
        docs = self.telemetry_repo.get_by_run(run_id)
        if not docs:
            logger.warning(f"[ReplayPlayer] run_id={run_id} has no stored telemetry")
            return
        self.current_run_id = run_id
        self.pipeline = DetectionPipeline()
        self.stop_flag = threading.Event()
        self.history = []
        self.thread = threading.Thread(target=self._play, args=(docs, speed), daemon=True)
        self.thread.start()

    def _play(self, docs, speed):
        while not self.stop_flag.is_set():
            for doc in docs:
                if self.stop_flag.is_set():
                    return
                flow, power, actuators = doc["flow"], doc["power"], doc.get("actuators", {})
                result = self.pipeline.process_sample(
                    ts=doc["ts"], q_in=flow["q_in_lpm"], q_out=flow["q_out_lpm"],
                    q_branch=flow.get("q_branch_lpm", 0.0), current_ma=power["current_ma"],
                    voltage_v=power.get("voltage", 12.0), pump_on=actuators.get("pump1", True),
                    servo_state_deg=actuators.get("servo_deg", 0), pressure_bar=doc.get("pressure_bar"),
                )
                response = build_response(result)
                self.latest_response = response
                self.latest_telemetry = doc
                self.history.append(doc)
                if len(self.history) > 120:
                    self.history.pop(0)
                time.sleep(1.0 / speed)

    def stop(self):
        if self.thread and self.thread.is_alive():
            self.stop_flag.set()
            self.thread.join(timeout=2)


# --- Mode state -------------------------------------------------------------
_mode = "replay"  # default to replay so the dashboard has data before the rig connects
_live_ingestor = LiveTelemetryIngestor()
_replay_player = ReplayPlayer()
_mqtt_client = None
_ground_truth_lock = threading.Lock()
_active_ground_truth = None


@app.on_event("startup")
def on_startup():
    global _mqtt_client
    try:
        _mqtt_client, _ = run_subscriber(ingestor=_live_ingestor, blocking=False)
    except Exception as e:
        logger.warning(f"[Startup] Could not connect to MQTT broker (live mode will show no data until it's reachable): {e}")

    # A cold start should show real replay telemetry rather than UI-invented
    # fallback values. If the run is not seeded, the API stays explicitly empty.
    _replay_player.start(os.getenv("DEFAULT_REPLAY_RUN", "RUN_001"))


class ModeRequest(BaseModel):
    mode: str
    run_id: Optional[str] = None


class GroundTruthStartRequest(BaseModel):
    tee_id: str
    clamp_turns: float
    leak_lpm: float
    demand_mode: str
    run_id: Optional[str] = None
    notes: str = ""


class CalibrationRequest(BaseModel):
    flow1_k: float
    flow2_k: float
    flow3_k: float
    bias_lpm: float
    sigma_lpm: float


@app.get("/api/health")
def health():
    mqtt_connected = bool(_mqtt_client and _mqtt_client.is_connected()) if _mqtt_client else False
    database_connected = False
    telemetry_records = 0
    try:
        db = get_db()
        db.command("ping")
        database_connected = True
        telemetry_records = db.telemetry.estimated_document_count()
    except Exception as exc:
        logger.warning(f"[Health] MongoDB unavailable: {exc}")

    now = time.time()
    last_seen = _live_ingestor.latest_received_at
    last_seen_age_sec = round(now - last_seen, 1) if last_seen else None
    device_online = bool(mqtt_connected and last_seen_age_sec is not None and last_seen_age_sec <= 15)
    device_status = _live_ingestor.latest_status or {}
    replay_ready = bool(_replay_player.latest_telemetry)
    data_source_ready = device_online if _mode == "live" else replay_ready

    return {
        "status": "ok" if database_connected and data_source_ready else "degraded",
        "mode": _mode,
        "mqtt_connected": mqtt_connected,
        "database_connected": database_connected,
        "telemetry_records": telemetry_records,
        "data_source_ready": data_source_ready,
        "simulation_mode": _mode == "replay" or _live_ingestor.latest_is_simulation,
        "replay_run_id": _replay_player.current_run_id if _mode == "replay" else None,
        "timestamp": int(now),
        "device": {
            "online": device_online,
            "device_id": device_status.get("device_id") or (
                _live_ingestor.latest_telemetry or {}
            ).get("device_id") or (
                _live_ingestor.latest_telemetry or {}
            ).get("device", "esp32-rig-01"),
            "last_seen_ts": int(last_seen) if last_seen else None,
            "last_seen_age_sec": last_seen_age_sec,
            "uptime_sec": device_status.get("uptime_sec"),
            "wifi_rssi": device_status.get("wifi_rssi"),
            "heap_free": device_status.get("heap_free"),
            "samples_received": _live_ingestor.samples_received,
        },
        "live_data_log": {
            "path": file_log_path(),
            "frames_logged": file_frames_logged(),
        },
    }


@app.get("/api/mode")
def get_mode():
    return {"mode": _mode, "run_id": _replay_player.current_run_id if _mode == "replay" else None}


@app.get("/api/calibration")
def calibration():
    return CalibrationRepository().data


@app.post("/api/calibration")
def update_calibration(req: CalibrationRequest):
    global _replay_player
    values = req.model_dump()
    if not all(100.0 <= values[key] <= 2000.0 for key in ("flow1_k", "flow2_k", "flow3_k")):
        return {"success": False, "error": "Flow K-factors must be between 100 and 2000 pulses/litre"}
    if not (-5.0 <= req.bias_lpm <= 5.0) or not (0.001 <= req.sigma_lpm <= 5.0):
        return {"success": False, "error": "Bias or sigma is outside the supported range"}

    repository = CalibrationRepository()
    repository.save_calibration({**values, "calibrated_at": time.time()})
    _live_ingestor.pipeline = DetectionPipeline()
    if _mode == "replay" and _replay_player.current_run_id:
        _replay_player.start(_replay_player.current_run_id)
    return {"success": True, "calibration": repository.data}


@app.get("/api/ground-truth/status")
def ground_truth_status():
    with _ground_truth_lock:
        return {"active": _active_ground_truth is not None, "event": _active_ground_truth}


@app.post("/api/ground-truth/start")
def ground_truth_start(req: GroundTruthStartRequest):
    global _active_ground_truth
    mqtt_connected = bool(_mqtt_client and _mqtt_client.is_connected()) if _mqtt_client else False
    sample_age = time.time() - _live_ingestor.latest_received_at if _live_ingestor.latest_received_at else None
    if _mode != "live" or not mqtt_connected or sample_age is None or sample_age > 15 or _live_ingestor.latest_is_simulation:
        return {
            "success": False,
            "error": "Physical ground truth can only be logged while a real ESP32 is the active live source.",
        }
    if req.tee_id not in ("TEE_A", "TEE_B", "TEE_C") or req.demand_mode not in ("steady", "variable"):
        return {"success": False, "error": "Invalid tee_id or demand_mode"}

    calibration_data = CalibrationRepository().data.get("clamp_calibration", {})
    turn_key = f"{req.clamp_turns:.2f}"
    calibrated_lpm = calibration_data.get(req.tee_id, {}).get(turn_key)
    if calibrated_lpm is None:
        return {"success": False, "error": "No calibrated leak rate exists for that tee/clamp position"}

    with _ground_truth_lock:
        if _active_ground_truth is not None:
            return {"success": False, "error": "A physical leak event is already active"}
        started_at = time.time()
        run_id = req.run_id or time.strftime("LIVE-%Y%m%d-%H%M%S")
        event = LeakEventRepository().create_event(
            start_ts=started_at,
            location_node=req.tee_id,
            severity_lpm=float(calibrated_lpm),
            run_id=run_id,
            is_ground_truth=True,
            notes=req.notes,
            metadata={"clamp_turns": req.clamp_turns, "demand_mode": req.demand_mode},
        )
        _active_ground_truth = {
            "event_id": str(event["_id"]),
            "run_id": run_id,
            "start_ts": started_at,
            "tee_id": req.tee_id,
            "clamp_turns": req.clamp_turns,
            "leak_lpm": float(calibrated_lpm),
            "demand_mode": req.demand_mode,
        }
        return {"success": True, "event": _active_ground_truth}


@app.post("/api/ground-truth/stop")
def ground_truth_stop():
    global _active_ground_truth
    with _ground_truth_lock:
        if _active_ground_truth is None:
            return {"success": False, "error": "No physical leak event is active"}
        from bson import ObjectId
        stopped_at = time.time()
        LeakEventRepository().close_event(ObjectId(_active_ground_truth["event_id"]), stopped_at)
        completed = {**_active_ground_truth, "stop_ts": stopped_at, "duration_sec": round(stopped_at - _active_ground_truth["start_ts"], 3)}
        _active_ground_truth = None
        return {"success": True, "event": completed}


@app.post("/api/mode")
def set_mode(req: ModeRequest):
    global _mode
    if req.mode not in ("live", "replay"):
        return {"success": False, "error": "mode must be 'live' or 'replay'"}
    _mode = req.mode
    if _mode == "replay":
        _replay_player.start(req.run_id or os.getenv("DEFAULT_REPLAY_RUN", "RUN_001"))
    return {
        "success": True,
        "mode": _mode,
        "run_id": _replay_player.current_run_id if _mode == "replay" else None,
    }


def _flatten_telemetry(raw: dict, response: Optional[dict], mode: str) -> Optional[dict]:
    """Normalizes either a raw MQTT payload (live) or a stored Mongo telemetry
    doc (replay) into the flat {q_in, q_out, ...} shape the dashboard's chart
    and summary components expect, regardless of source."""
    if raw is None:
        return None

    if mode == "live":
        dto = TelemetryDTO.from_dict(raw)
        q_in, q_out, q_branch = dto.flow.q_in_lpm, dto.flow.q_out_lpm, dto.flow.q_branch_lpm
        current_ma, voltage_v = dto.power.current_ma, dto.power.voltage
        pump1_on, pump2_on = dto.actuators.pump1, dto.actuators.pump2
        pump_on = pump1_on or pump2_on
        leak_active = bool(response and response.get("is_alarm"))
        servo_deg = dto.actuators.servo_deg
        device_id = dto.device_id
        ts_source = raw.get("ts_source", "device_ntp")
        ts = raw.get("ts")
    else:
        flow, power, actuators = raw.get("flow", {}), raw.get("power", {}), raw.get("actuators", {})
        q_in, q_out, q_branch = flow.get("q_in_lpm", 0.0), flow.get("q_out_lpm", 0.0), flow.get("q_branch_lpm", 0.0)
        current_ma, voltage_v = power.get("current_ma", 0.0), power.get("voltage", 0.0)
        pump1_on, pump2_on = actuators.get("pump1", True), actuators.get("pump2", False)
        pump_on = pump1_on or pump2_on
        leak_active = bool(response and response.get("is_alarm"))
        servo_deg = actuators.get("servo_deg", 0)
        device_id = raw.get("device_id", "replay")
        ts_source = "logged"
        ts = raw.get("ts")

    if response:
        residual = response.get("residual")
    elif raw.get("residual") is not None:
        residual = raw.get("residual")
    else:
        include_branch = config_loader.get("hydraulics.topology", "recombined_branch") == "metered_outflow"
        bias_lpm = float(config_loader.get("hydraulics.zero_leak_bias_lpm", 0.02))
        residual = round(q_in - q_out - (q_branch if include_branch else 0.0) - bias_lpm, 3)
    pressure_bar = response.get("pressure", {}).get("pressure_bar") if response else raw.get("pressure_bar")

    return {
        "ts": ts, "q_in": q_in, "q_out": q_out, "q_branch": q_branch,
        "current_ma": current_ma, "voltage_v": voltage_v, "residual": residual,
        "pressure_bar": pressure_bar, "pump_on": pump_on, "leak_active": leak_active,
        "pump1_on": pump1_on, "pump2_on": pump2_on,
        "servo_deg": servo_deg, "device_id": device_id, "ts_source": ts_source,
    }


@app.get("/api/telemetry")
def get_telemetry():
    source = _live_ingestor if _mode == "live" else _replay_player
    flat = _flatten_telemetry(source.latest_telemetry, source.latest_response, _mode)
    return {
        "mode": _mode,
        "latest": flat,
        "pump_on": flat["pump_on"] if flat else True,
        "leak_active": flat["leak_active"] if flat else False,
        "evaluation": source.latest_response,
    }


@app.get("/api/telemetry/history")
def get_telemetry_history():
    if _mode == "live":
        docs = TelemetryRepository().get_recent(limit=120, run_id=None)
        return [_flatten_telemetry(d, None, "replay") for d in docs]
    return [_flatten_telemetry(d, None, "replay") for d in _replay_player.history]


@app.get("/api/replay/runs")
def list_replay_runs():
    from backend.repositories.db import get_db
    db = get_db()
    return list(db.experiment_runs.find({}, {"_id": 0}))


@app.post("/api/replay/evaluate")
def evaluate_replay(body: dict):
    run_id = body.get("run_id")
    if not run_id:
        return {"error": "run_id is required"}
    runner = ReplayRunner()
    return runner.run(run_id)


_ZONE_CONFIDENCE_NUMERIC = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3, "NONE": 0.0}


@app.get("/api/localization/current")
def localization_current():
    source = _live_ingestor if _mode == "live" else _replay_player
    resp = source.latest_response
    if not resp or resp.get("zone") in (None, "NONE"):
        return {"localized": False, "node": "NONE", "branch": "NONE", "distance_meters": 0.0, "confidence": 0.0}
    zone = resp["zone"]
    return {
        "localized": True,
        "node": zone,
        "branch": zone,
        "distance_meters": None,  # not measurable without a distributed pressure/flow sensor network
        "confidence": _ZONE_CONFIDENCE_NUMERIC.get(resp["zone_confidence"], 0.0),
        "likelihood_score": resp["likelihood_score"],
        "verification_required": True,
        "recommended_next_step": f"Inspect {zone} and compare handheld flow/pressure readings with the event window.",
    }


@app.get("/api/work-orders")
def list_work_orders():
    return WorkOrderRepository().list_all()


@app.post("/api/work-orders/dispatch")
def dispatch_work_order(body: dict):
    scheduler = CPSatWorkOrderScheduler()
    leak = {
        "id": body.get("leak_event_id", int(time.time())),
        "location_node": body.get("location", "Branch_A"),
        "severity_lpm": float(body.get("severity", 1.25)),
    }
    work_orders = scheduler.optimize_schedule([leak])
    wo = work_orders[0]
    wo["id"] = wo.pop("work_order_id")
    WorkOrderRepository().insert(wo)
    return {"success": True, "work_order": wo}
