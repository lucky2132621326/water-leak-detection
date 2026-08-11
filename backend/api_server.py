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

from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
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
from backend.alerts.alert_service import get_alert_service
from backend.impact.impact_service import ImpactService, analyze_impact
from backend.impact.severity import SeverityClassifier
from backend.reports.experiment_report import ExperimentReportGenerator
from backend.config.config_loader import impact_loader
from backend.utils.logger import logger
from backend.config.config_loader import config_loader

app = FastAPI(title="Water Leak Detection API")

# Wildcard CORS on an API with unauthenticated mutating routes (mode switch,
# work-order dispatch, alert disposition, ground-truth logging) lets any
# origin script the whole rig. This service is only ever meant to be called
# by server.ts's proxy and local dev tooling, so the allowlist is explicit —
# override with CORS_ALLOWED_ORIGINS (comma-separated) for other setups.
_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_allowed_origins = [o.strip() for o in os.getenv("CORS_ALLOWED_ORIGINS", _default_origins).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_allowed_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# State-changing routes (mode switch, calibration, ground-truth logging,
# work-order dispatch, alert disposition) require this key. server.ts holds
# it server-side and attaches it when proxying — the browser never sees it,
# so nothing changes for the dashboard itself. This closes "any script on
# the same network can POST directly to :8001" without standing up a full
# user-account system, which would be disproportionate for a single-rig
# ops tool with no multi-tenancy.
_API_KEY = os.getenv("API_KEY", "local-dev-key-change-me")
if _API_KEY == "local-dev-key-change-me":
    logger.warning(
        "[Security] API_KEY not set — using the insecure default. Set API_KEY "
        "(and the matching value in server.ts's environment) before exposing "
        "this service beyond localhost."
    )


def require_api_key(x_api_key: Optional[str] = Header(None)):
    if x_api_key != _API_KEY:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


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
                    vibration=doc.get("vibration"), water_temp_c=(doc.get("temp") or {}).get("water_c"),
                )
                response = build_response(result)
                get_alert_service().ingest(response, source="replay", run_id=self.current_run_id)
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

# Impact analysis and the alert store are stateless-ish singletons; built lazily
# so importing this module never requires MongoDB to be reachable.
_impact_singleton = None
_report_generator = None


def _alerts():
    return get_alert_service()


def _impact_service() -> ImpactService:
    global _impact_singleton
    if _impact_singleton is None:
        _impact_singleton = ImpactService()
    return _impact_singleton


def _reports() -> ExperimentReportGenerator:
    global _report_generator
    if _report_generator is None:
        _report_generator = ExperimentReportGenerator()
    return _report_generator


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
    vib_baseline_band_mid: float = 0.015
    temp_k_coeff: float = 0.0


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


@app.post("/api/calibration", dependencies=[Depends(require_api_key)])
def update_calibration(req: CalibrationRequest):
    global _replay_player
    values = req.model_dump()
    if not all(100.0 <= values[key] <= 2000.0 for key in ("flow1_k", "flow2_k", "flow3_k")):
        return {"success": False, "error": "Flow K-factors must be between 100 and 2000 pulses/litre"}
    if not (-5.0 <= req.bias_lpm <= 5.0) or not (0.001 <= req.sigma_lpm <= 5.0):
        return {"success": False, "error": "Bias or sigma is outside the supported range"}
    if not (0.0 < req.vib_baseline_band_mid <= 1.0):
        return {"success": False, "error": "Vibration baseline band_mid must be between 0 and 1.0"}
    if not (-1.0 <= req.temp_k_coeff <= 1.0):
        return {"success": False, "error": "Temperature K-factor coefficient must be between -1.0 and 1.0"}

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


@app.post("/api/ground-truth/start", dependencies=[Depends(require_api_key)])
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


@app.post("/api/ground-truth/stop", dependencies=[Depends(require_api_key)])
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


@app.post("/api/mode", dependencies=[Depends(require_api_key)])
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
    response = source.latest_response

    # The residual IS the estimated leak rate — water entering the zone that
    # never left it. Attaching its impact summary here means every view reading
    # /api/telemetry shows the same severity/loss figures as the Alert Center.
    leak_rate = _alerts().leak_rate_from(response) if (response and response.get("is_alarm")) else 0.0

    return {
        "mode": _mode,
        "latest": flat,
        "pump_on": flat["pump_on"] if flat else True,
        "leak_active": flat["leak_active"] if flat else False,
        "evaluation": response,
        "leak_rate_lpm": round(leak_rate, 3),
        "impact": _impact_service().summarize(leak_rate),
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


@app.post("/api/work-orders/dispatch", dependencies=[Depends(require_api_key)])
def dispatch_work_order(body: dict):
    scheduler = CPSatWorkOrderScheduler()

    # A work order can be raised straight from an Alert Center incident, in
    # which case the severity comes from the incident's peak observed rate
    # rather than an operator retyping it.
    alert_id = body.get("alert_id")
    alert = _alerts().get(alert_id) if alert_id else None
    if alert:
        location = alert["zone"]
        severity = alert["peak_leak_rate_lpm"]
        leak_event_id = alert["alert_id"]
    else:
        location = body.get("location", "Branch_A")
        severity = float(body.get("severity", 1.25))
        leak_event_id = body.get("leak_event_id", int(time.time()))

    work_orders = scheduler.optimize_schedule([{
        "id": leak_event_id, "location_node": location, "severity_lpm": severity,
    }])
    wo = work_orders[0]
    wo["id"] = wo.pop("work_order_id")
    wo["alert_id"] = alert_id
    wo["impact"] = _impact_service().summarize(severity)
    WorkOrderRepository().insert(wo)
    # insert() lets Mongo stamp an ObjectId onto the dict, which is not
    # JSON-serializable — drop it before returning.
    wo.pop("_id", None)
    return {"success": True, "work_order": wo}


# --- Impact analysis --------------------------------------------------------

@app.get("/api/impact/config")
def impact_config():
    """Tariff, severity bands and simulator options — lets the frontend render
    the controls without hardcoding values the backend owns."""
    classifier = SeverityClassifier()
    return {
        "currency_symbol": impact_loader.get("tariff.currency_symbol", "₹"),
        "rate_per_kilolitre": impact_loader.get("tariff.rate_per_kilolitre", 20.0),
        "severity_bands": classifier.describe_bands(),
        "delay_options_days": impact_loader.get("progression.delay_options_days", [1, 7, 30, 90, 365]),
        "default_delay_days": impact_loader.get("progression.default_delay_days", 30),
        "equivalents": impact_loader.get("equivalents", {}),
    }


@app.get("/api/impact/current")
def impact_current():
    """Impact of whatever the detector is seeing right now — this is what the
    dashboard's 'Analyze Impact' button pre-fills the simulator from."""
    source = _live_ingestor if _mode == "live" else _replay_player
    resp = source.latest_response
    rate = _alerts().leak_rate_from(resp) if (resp and resp.get("is_alarm")) else 0.0
    return {
        "leak_detected": bool(resp and resp.get("is_alarm")),
        "zone": (resp or {}).get("zone", "NONE"),
        "confidence_tier": (resp or {}).get("confidence_tier", "NONE"),
        "likelihood_score": (resp or {}).get("likelihood_score", 0.0),
        "analysis": analyze_impact(rate),
    }


@app.post("/api/impact/simulate")
def impact_simulate(body: dict):
    """The interactive 'what if we ignore it?' simulator. Every parameter is
    optional and falls back to the configured default."""
    try:
        rate = float(body.get("leak_rate_lpm", 0.0) or 0.0)
    except (TypeError, ValueError):
        return {"error": "leak_rate_lpm must be a number"}

    delay = body.get("repair_delay_days")
    tariff = body.get("tariff_per_kl")
    try:
        delay = float(delay) if delay is not None else None
        tariff = float(tariff) if tariff is not None else None
    except (TypeError, ValueError):
        return {"error": "repair_delay_days and tariff_per_kl must be numbers"}

    if tariff is not None and tariff <= 0:
        return {"error": "tariff_per_kl must be greater than zero"}

    return analyze_impact(rate, repair_delay_days=delay, tariff_per_kl=tariff)


# --- Alert Center -----------------------------------------------------------

def _parse_float(value):
    try:
        return float(value) if value not in (None, "", "ALL") else None
    except (TypeError, ValueError):
        return None


@app.get("/api/alerts")
def list_alerts(status: Optional[str] = None, zone: Optional[str] = None,
                severity: Optional[str] = None, min_confidence: Optional[str] = None,
                since_ts: Optional[str] = None, until_ts: Optional[str] = None,
                search: Optional[str] = None, limit: int = 200):
    return _alerts().query(
        status=status, zone=zone, severity=severity,
        min_confidence=_parse_float(min_confidence),
        since_ts=_parse_float(since_ts), until_ts=_parse_float(until_ts),
        search=search, limit=limit,
    )


@app.get("/api/alerts/summary")
def alerts_summary():
    svc = _alerts()
    return {"counts": svc.counts(), "zones": svc.zones(), "timeline": svc.timeline()}


@app.post("/api/alerts/{alert_id}/resolve", dependencies=[Depends(require_api_key)])
def resolve_alert(alert_id: str, body: dict = None):
    alert = _alerts().resolve(alert_id, note=(body or {}).get("note", ""))
    if not alert:
        return {"success": False, "error": f"Unknown alert '{alert_id}'"}
    return {"success": True, "alert": alert, "savings": _alerts().savings()}


@app.post("/api/alerts/{alert_id}/false-positive", dependencies=[Depends(require_api_key)])
def false_positive_alert(alert_id: str, body: dict = None):
    alert = _alerts().mark_false_positive(alert_id, note=(body or {}).get("note", ""))
    if not alert:
        return {"success": False, "error": f"Unknown alert '{alert_id}'"}
    return {"success": True, "alert": alert, "savings": _alerts().savings()}


@app.post("/api/alerts/{alert_id}/reopen", dependencies=[Depends(require_api_key)])
def reopen_alert(alert_id: str):
    alert = _alerts().reopen(alert_id)
    if not alert:
        return {"success": False, "error": f"Unknown alert '{alert_id}'"}
    return {"success": True, "alert": alert, "savings": _alerts().savings()}


@app.get("/api/savings")
def savings():
    """Water Savings Counter — the utility-KPI view of what repairs achieved."""
    return _alerts().savings()


# --- Automatic experiment reports -------------------------------------------

@app.get("/api/reports/experiment/{run_id}")
def experiment_report(run_id: str):
    return _reports().build(run_id)


@app.get("/api/reports/experiment/{run_id}/html", response_class=HTMLResponse)
def experiment_report_html(run_id: str):
    """Standalone printable report. The browser's Save-as-PDF turns this into
    the PDF deliverable without pulling in a PDF toolchain."""
    generator = _reports()
    report = generator.build(run_id)
    body = generator.render_html(report)
    return HTMLResponse(
        f"<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        f"<meta name='viewport' content='width=device-width, initial-scale=1'>"
        f"<title>Experiment Report — {run_id}</title></head><body>{body}</body></html>"
    )
