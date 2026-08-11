"""FastAPI Bridge

Owns the operating-mode switch. There are exactly two modes — Mock Data and
Live Sensor — and they differ only in which TelemetrySource is attached. Every
sample from either source runs through the same TelemetryIngestor and
DetectionPipeline, so switching modes changes where data comes from, never how
it is evaluated. See docs/OPERATING_MODES.md.

Run with: uvicorn backend.api_server:app --host 0.0.0.0 --port 8000
"""
import json
import os
import threading
import time
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from backend.ingestion import TelemetryIngestor, flatten_sample
from backend.mode import MODE_LIVE, MODE_MOCK, set_active_mode
from backend.ingestion.mqtt_source import MqttTelemetrySource
from backend.mock.mock_source import MockTelemetrySource
from backend.mock.scenarios import get_scenario, list_scenarios, scenario_from_dict
from backend.mock.leak_control import PRESETS, VALID_LOCATIONS, MAIN as MAIN_TRUNK
from backend.pipeline import DetectionPipeline
from backend.response.response_builder import build_response
from backend.repositories.telemetry_repository import TelemetryRepository
from backend.repositories.detection_repository import LeakEventRepository, WorkOrderRepository
from backend.benchmark.benchmark_scorer import BenchmarkScorer
from backend.scheduler.cp_sat_scheduler import CPSatWorkOrderScheduler
from backend.localization.localization_service import LocalizationService
from backend.alerts.alert_service import get_alert_service
from backend.analytics.benchmark_analytics import BenchmarkAnalytics
from backend.fusion.fusion_engine import FusionEngine
from backend.impact.impact_service import ImpactService, analyze_impact
from backend.impact.severity import SeverityClassifier
from backend.reports.experiment_report import ExperimentReportGenerator
from backend.config.config_loader import impact_loader, thresholds_loader, config_loader
from backend.services.experiment_service import get_experiment_service
from backend.utils.logger import logger

app = FastAPI(title="Water Leak Detection API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# --- Operating modes ---------------------------------------------------------
#
# Exactly two, differing ONLY in where telemetry comes from. Everything after
# `ingestor.ingest(raw)` — validation, DTO, detectors, fusion, confidence,
# localization, alerts, impact — is one shared code path, so a mock sample and
# a rig sample are indistinguishable to the detection logic.
#
#   MOCK : MockTelemetrySource (generated scenarios)
#   LIVE : MqttTelemetrySource (ESP32 over MQTT)

_mode = MODE_MOCK  # start in mock so the dashboard is useful before a rig exists
_ingestor = TelemetryIngestor(source_name=MODE_MOCK)
_live_source = MqttTelemetrySource()
_mock_source = None
_mode_lock = threading.RLock()

# Built lazily so importing this module never requires MongoDB to be reachable.
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


def _active_source():
    return _live_source if _mode == MODE_LIVE else _mock_source


def _stop_all_sources():
    global _mock_source
    if _mock_source:
        _mock_source.stop()
        _mock_source = None
    _live_source.stop()


def _switch_mode(mode: str, scenario_id: str = None, speed: float = 4.0, loop: bool = True):
    """Change operating mode.

    Detector state is reset on every switch. Every detector is stateful — the
    mass-balance rolling window, the CUSUM accumulator, the MNF and acoustic
    baselines — so carrying live-rig state into a mock scenario (or the
    reverse) would evaluate the first samples against a baseline learned under
    entirely different conditions.
    """
    global _mode, _mock_source, _ingestor

    with _mode_lock:
        _stop_all_sources()
        _mode = mode
        # Repoint the data store BEFORE building the ingestor. Live and mock use
        # physically separate databases, and every repository resolves its handle
        # through the active mode — so this one call is what keeps rig data out
        # of the synthetic store and vice versa.
        set_active_mode(mode)
        _ingestor = TelemetryIngestor(source_name=mode)

        if mode == MODE_LIVE:
            _live_source.start(_ingestor)
            return {"success": True, "mode": mode, "source": _live_source.describe()}

        scenario = get_scenario(scenario_id or "sudden_leak")
        if scenario is None:
            return {"success": False, "error": f"Unknown scenario '{scenario_id}'"}
        # The interactive scenario streams in real time so timestamps advance
        # monotonically like a rig; scripted scenarios keep scenario-relative
        # time so they stay reproducible.
        interactive = scenario.id == "manual_control"
        _mock_source = MockTelemetrySource(
            scenario, speed=speed, loop=loop,
            run_id=f"MOCK_{scenario.id}",
            realtime=interactive,
            persist_ground_truth=not interactive)
        _mock_source.start(_ingestor)
        return {"success": True, "mode": mode, "source": _mock_source.describe()}


@app.on_event("startup")
def on_startup():
    """Boot into Mock Data Mode so the dashboard is immediately useful. Live
    mode is entered explicitly, which also avoids a startup stall when no
    broker is present."""
    _switch_mode(MODE_MOCK, scenario_id="manual_control", speed=1.0)


class ModeRequest(BaseModel):
    mode: str
    scenario_id: Optional[str] = None
    speed: Optional[float] = None
    loop: Optional[bool] = None


@app.get("/api/health")
def health():
    return {
        "status": "ok",
        "mode": _mode,
        "mqtt_connected": _live_source.is_running,
        "timestamp": int(time.time()),
    }


@app.get("/api/mode")
def get_mode():
    source = _active_source()
    return {
        "mode": _mode,
        "modes": [MODE_MOCK, MODE_LIVE],
        "source": source.describe() if source else {"source": _mode, "running": False},
        "sample_count": _ingestor.sample_count,
        "rejected_count": _ingestor.rejected_count,
    }


@app.post("/api/mode")
def set_mode(req: ModeRequest):
    if req.mode not in (MODE_MOCK, MODE_LIVE):
        return {"success": False, "error": f"mode must be '{MODE_MOCK}' or '{MODE_LIVE}'"}
    return _switch_mode(req.mode, scenario_id=req.scenario_id,
                        speed=req.speed or 4.0,
                        loop=True if req.loop is None else req.loop)


# --- Mock scenarios ----------------------------------------------------------

@app.get("/api/scenarios")
def get_scenarios():
    return {"scenarios": list_scenarios(), "active": (_mock_source.scenario.id if _mock_source else None)}


@app.post("/api/scenarios/run")
def run_scenario(body: dict):
    """Evaluate a scenario end-to-end immediately and score it against its own
    ground truth. Runs through the same ingestor the dashboard uses, on an
    isolated instance so an in-progress live/mock stream is not disturbed."""
    scenario_id = body.get("scenario_id")
    scenario = get_scenario(scenario_id) if scenario_id else None
    if scenario is None and body.get("scenario"):
        try:
            scenario = scenario_from_dict(body["scenario"])
        except (TypeError, ValueError) as e:
            return {"success": False, "error": f"Invalid scenario definition: {e}"}
    if scenario is None:
        return {"success": False, "error": f"Unknown scenario '{scenario_id}'"}

    persist = bool(body.get("persist", True))
    run_id = body.get("run_id") or f"MOCK_{scenario.id}"
    scratch = TelemetryIngestor(source_name=MODE_MOCK, persist=persist)
    source = MockTelemetrySource(scenario, run_id=run_id, persist_ground_truth=persist)
    result = source.run_batch(scratch)
    result["success"] = True
    result["persisted"] = persist
    _analytics_cache.clear()  # a new scored run invalidates cached aggregates
    return result


@app.get("/api/telemetry")
def get_telemetry():
    snap = _ingestor.snapshot()
    flat = snap["latest"]
    response = snap["evaluation"]

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
    # One in-memory history for whichever mode is active; both are populated by
    # the same ingestor, so there is no per-mode branch here any more.
    return _ingestor.recent_history()


@app.get("/api/benchmark/runs")
def list_benchmark_runs():
    from backend.repositories.db import get_db
    db = get_db()
    return list(db.experiment_runs.find({}, {"_id": 0}))


@app.post("/api/benchmark/evaluate")
def evaluate_benchmark(body: dict):
    run_id = body.get("run_id")
    if not run_id:
        return {"error": "run_id is required"}
    runner = BenchmarkScorer()
    return runner.run(run_id)


_ZONE_CONFIDENCE_NUMERIC = {"HIGH": 0.9, "MEDIUM": 0.6, "LOW": 0.3, "NONE": 0.0}
_ZONE_ISOLATION_VALVE = {"Branch_A": "SOLENOID_VALVE_2", "Branch_B": "SOLENOID_VALVE_3", "Main_Trunk": "MAIN_ISOLATION_VALVE"}


@app.get("/api/localization/current")
def localization_current():
    resp = _ingestor.latest_response
    if not resp or resp.get("zone") in (None, "NONE"):
        return {"localized": False, "node": "NONE", "branch": "NONE", "distance_meters": 0.0, "confidence": 0.0}
    zone = resp["zone"]
    return {
        "localized": True,
        "node": zone,
        "branch": zone,
        "distance_meters": None,  # not measurable without a distributed flow/acoustic sensor network
        "confidence": _ZONE_CONFIDENCE_NUMERIC.get(resp["zone_confidence"], 0.0),
        "isolation_valve_suggested": _ZONE_ISOLATION_VALVE.get(zone),
        "likelihood_score": resp["likelihood_score"],
    }


def _publish_command(payload: dict) -> tuple[bool, str]:
    """Publish to the rig's `rig/cmd` topic (docs/MQTT_SPEC.md). The firmware
    subscribes to it; this is the only path by which the dashboard can actuate
    hardware, and it is available in live mode only."""
    return _live_source.publish_command({**payload, "ts": int(time.time())})


@app.post("/api/leak/toggle")
def leak_toggle(body: dict):
    """Bench controls — the SAME operator actions in both modes.

    The two modes differ only in what the command reaches:
      * Live Sensor Mode  → publishes to `rig/cmd`, actuating the real valve.
      * Mock Data Mode    → mutates the generator's leak state, so the next
                            synthesized sample already reflects it.

    Either way the resulting telemetry travels the identical
    ingest → validate → DTO → detect → fuse → localize → alert → impact path.
    An earlier version refused these in Mock Data Mode, reasoning that mock
    leaks belong in the scenario. That was wrong: a generator has no hardware
    constraint, and refusing made the mock environment un-interactive.
    """
    action = str(body.get("action", "")).upper()

    # --- pump ---------------------------------------------------------------
    if "pump_state" in body:
        if _mode == MODE_LIVE:
            ok, msg = _publish_command({"cmd": "SET_PUMP", "state": "ON" if body["pump_state"] else "OFF"})
            return {"success": ok, "message": msg}
        return {"success": False,
                "error": "Pump control is not modelled in Mock Data Mode — the generator "
                         "assumes the pump runs continuously."}

    # --- air bubbles --------------------------------------------------------
    if "air_bubbles" in body:
        if _mode == MODE_LIVE:
            ok, msg = _publish_command({"cmd": "SET_AIR_BUBBLES", "state": "ON" if body["air_bubbles"] else "OFF"})
            return {"success": ok, "message": msg}
        return {"success": False,
                "error": "Air-bubble injection is a scenario fault in Mock Data Mode — "
                         "run the 'sensor_noise' or 'sensor_fault' scenario instead."}

    # --- leak valve ---------------------------------------------------------
    if action not in ("OPEN", "CLOSE"):
        return {"success": False,
                "error": "Unrecognized command. Expected action OPEN/CLOSE, pump_state, or air_bubbles."}

    location = body.get("location") or MAIN_TRUNK
    try:
        size = float(body.get("size", PRESETS["medium"]))
        ramp = float(body.get("ramp_sec", 0.0))
    except (TypeError, ValueError):
        return {"success": False, "error": "size and ramp_sec must be numbers"}

    if _mode == MODE_LIVE:
        payload = ({"cmd": "SET_VALVE", "valve_id": "leak_valve_1", "state": "OPEN",
                    "target_lpm": size, "location": location}
                   if action == "OPEN" else
                   {"cmd": "SET_VALVE", "valve_id": "leak_valve_1", "state": "CLOSE"})
        ok, msg = _publish_command(payload)
        return {"success": ok, "message": msg, "mode": _mode,
                "target_lpm": size if action == "OPEN" else 0.0}

    if _mock_source is None:
        return {"success": False, "error": "No mock stream is running. Start one from Mock Scenarios."}

    if action == "OPEN":
        state = _mock_source.control.open(size, location=location, ramp_sec=ramp)
        message = (f"Leak opened on {state['location']} at {state['rate_lpm']} L/min"
                   + (f" (ramping over {ramp:.0f}s)" if ramp else ""))
    else:
        state = _mock_source.control.close()
        message = "Leak closed — telemetry returns to baseline; watch the detectors recover."

    logger.info(f"[MockControl] {message}")
    return {"success": True, "mode": _mode, "message": message, "leak_control": state}


@app.get("/api/mock/control")
def mock_control_state():
    """Current mock leak state, for the bench controls to reflect."""
    if _mock_source is None:
        return {"available": False,
                "reason": "Mock Data Mode is not running." if _mode != MODE_MOCK
                          else "No mock stream is active.",
                "mode": _mode}
    return {"available": True, "mode": _mode,
            "scenario": _mock_source.scenario.summary(),
            "leak_control": _mock_source.control.snapshot()}


@app.post("/api/mock/control/release")
def mock_control_release():
    """Return leak control to the scenario script."""
    if _mock_source is None:
        return {"success": False, "error": "No mock stream is running."}
    return {"success": True, "leak_control": _mock_source.control.release()}


# --- Experiment control & ground truth ---------------------------------------

@app.get("/api/experiments/status")
def experiment_status():
    return get_experiment_service().status()


@app.post("/api/experiments/start")
def experiment_start(body: dict):
    return get_experiment_service().start_run(
        run_id=body.get("run_id"),
        operator=body.get("operator", "unknown"),
        location=body.get("location", "Branch_A"),
        leak_size_lpm=body.get("leak_size_lpm", 0.0),
        pump_mode=body.get("pump_mode", "Constant 12V"),
        notes=body.get("notes", ""),
    )


@app.post("/api/experiments/stop")
def experiment_stop():
    return get_experiment_service().stop_run()


@app.post("/api/experiments/ground-truth/start")
def ground_truth_start(body: dict = None):
    body = body or {}
    return get_experiment_service().start_ground_truth_leak(
        location=body.get("location"),
        severity_lpm=body.get("severity_lpm"),
        notes=body.get("notes", ""),
    )


@app.post("/api/experiments/ground-truth/stop")
def ground_truth_stop():
    return get_experiment_service().stop_ground_truth_leak()


@app.get("/api/work-orders")
def list_work_orders():
    return WorkOrderRepository().list_all()


@app.post("/api/work-orders/dispatch")
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

    # Schedule the new leak alongside every still-open incident, so CP-SAT can
    # sequence crews across the real outstanding workload rather than treating
    # each dispatch as if it were the only job.
    pending = [{
        "id": a["alert_id"], "location_node": a["zone"], "severity_lpm": a["peak_leak_rate_lpm"],
    } for a in _alerts().query(status="ACTIVE") if a["alert_id"] != alert_id]

    work_orders = scheduler.optimize_schedule(
        [{"id": leak_event_id, "location_node": location, "severity_lpm": severity}] + pending
    )
    wo = next((w for w in work_orders if w["leak_id"] == leak_event_id), work_orders[0])
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
    resp = _ingestor.latest_response
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


@app.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str, body: dict = None):
    alert = _alerts().resolve(alert_id, note=(body or {}).get("note", ""))
    if not alert:
        return {"success": False, "error": f"Unknown alert '{alert_id}'"}
    return {"success": True, "alert": alert, "savings": _alerts().savings()}


@app.post("/api/alerts/{alert_id}/false-positive")
def false_positive_alert(alert_id: str, body: dict = None):
    alert = _alerts().mark_false_positive(alert_id, note=(body or {}).get("note", ""))
    if not alert:
        return {"success": False, "error": f"Unknown alert '{alert_id}'"}
    return {"success": True, "alert": alert, "savings": _alerts().savings()}


@app.post("/api/alerts/{alert_id}/reopen")
def reopen_alert(alert_id: str):
    alert = _alerts().reopen(alert_id)
    if not alert:
        return {"success": False, "error": f"Unknown alert '{alert_id}'"}
    return {"success": True, "alert": alert, "savings": _alerts().savings()}


@app.get("/api/savings")
def savings(include_mock: bool = False):
    """Water Savings Counter. Mock incidents are excluded unless asked for —
    see AlertService.savings()."""
    return _alerts().savings(include_mock=include_mock)


# --- Calibration -------------------------------------------------------------

@app.get("/api/calibration")
def get_calibration():
    from backend.calibration.calibration_repository import CalibrationRepository
    data = dict(CalibrationRepository().data)
    # K-factors are compiled into the firmware and applied on-device. Storing a
    # different value here would not change what the ESP32 reports, so the API
    # says so explicitly rather than implying the dashboard can retune the rig.
    data["note"] = (
        "K-factors are applied on-device from firmware/src/config.h. Values saved here "
        "are the recorded field-calibration record; to change what the rig reports, "
        "update config.h and reflash."
    )
    return data


@app.post("/api/calibration")
def save_calibration(body: dict):
    from backend.calibration.calibration_repository import CalibrationRepository
    allowed = {"flow1_k", "flow2_k", "flow3_k", "bias_lpm", "sigma_lpm",
               "ina219_no_load_ma", "ina219_load_slope"}
    update = {}
    for key, value in (body or {}).items():
        if key not in allowed:
            continue
        try:
            update[key] = float(value)
        except (TypeError, ValueError):
            return {"success": False, "error": f"{key} must be a number"}

    if not update:
        return {"success": False, "error": f"No recognized fields. Expected any of: {sorted(allowed)}"}

    update["calibrated_at"] = time.time()
    update["source"] = "field calibration"
    repo = CalibrationRepository()
    repo.save_calibration(update)
    return {"success": True, "calibration": repo.data,
            "note": "Recorded. K-factors still require a firmware reflash to take effect on the rig."}


# --- Runtime configuration & self-test ---------------------------------------

@app.get("/api/config")
def get_config():
    """Effective runtime configuration — reports the values actually in force,
    including which file won where two files disagree."""
    return {
        "mqtt": {
            "host": config_loader.get("mqtt.host", "localhost"),
            "port": config_loader.get("mqtt.port", 1883),
            "topic": config_loader.get("mqtt.topic", "rig/telemetry"),
            "cmd_topic": config_loader.get("mqtt.cmd_topic", "rig/cmd"),
        },
        "database": {
            "uri": os.getenv("MONGO_URI", "mongodb://localhost:27017"),
            "name": os.getenv("MONGO_DB_NAME", "water_leak_detection"),
            "source": "MONGO_URI environment variable (settings.yaml database.uri is not read)",
        },
        "detector": {
            "sigma_multiplier": thresholds_loader.get("mass_balance.sigma_threshold", 3.0),
            "persistence_samples": thresholds_loader.get("mass_balance.persistence_seconds", 5),
            "current_drop_threshold_ma": thresholds_loader.get("current_signature.drop_threshold_ma", 25.0),
            "cusum_k": thresholds_loader.get("cusum.k_allowance", 0.15),
            "cusum_h": thresholds_loader.get("cusum.h_decision_threshold", 5.0),
            "source": "backend/config/thresholds.yaml",
        },
        "editable": False,
        "note": (
            "Detector thresholds are read from thresholds.yaml at startup. Edit that file "
            "and restart the API to change them — they are deliberately not writable over "
            "HTTP so a running experiment cannot have its detection criteria changed mid-run."
        ),
    }


@app.post("/api/self-test")
def run_self_test():
    """Runs the real backend self-test (backend/self_test/system_self_test.py)
    and returns its captured output."""
    import io
    import contextlib
    from backend.self_test.system_self_test import run_self_test as _run

    buffer = io.StringIO()
    passed = False
    try:
        with contextlib.redirect_stdout(buffer):
            _run()
        passed = "PASSED" in buffer.getvalue().upper()
    except Exception as e:
        buffer.write(f"\nSELF-TEST FAILED WITH EXCEPTION: {e}")

    return {"passed": passed, "output": buffer.getvalue(), "timestamp": int(time.time())}


# --- Benchmark analytics (computed, never authored) -------------------------

_analytics_cache = {"summary": None, "roc": None}


@app.get("/api/analytics/summary")
def analytics_summary(refresh: bool = False):
    """Re-scores every stored run. That is expensive, so the result is
    cached until explicitly refreshed — the underlying runs are immutable."""
    if _analytics_cache["summary"] is None or refresh:
        _analytics_cache["summary"] = BenchmarkAnalytics().summary()
    return _analytics_cache["summary"]


@app.get("/api/analytics/roc")
def analytics_roc(run_id: Optional[str] = None, refresh: bool = False):
    key = f"roc:{run_id}"
    if _analytics_cache.get(key) is None or refresh:
        _analytics_cache[key] = BenchmarkAnalytics().roc(run_id)
    return _analytics_cache[key]


@app.get("/api/detectors/config")
def detectors_config():
    """The fusion weights actually in force, so the UI can display the formula
    it is really running rather than a hand-copied version of it."""
    engine = FusionEngine()
    return {
        "weights": engine.weights,
        "formula": " + ".join(f"{w:.2f}·{k}" for k, w in engine.weights.items()),
        "thresholds": {
            "mass_balance_sigma": thresholds_loader.get("mass_balance.sigma_threshold", 3.0),
            "mass_balance_persistence_samples": thresholds_loader.get("mass_balance.persistence_seconds", 5),
            "current_drop_ma": thresholds_loader.get("current_signature.drop_threshold_ma", 25.0),
            "cusum_k": thresholds_loader.get("cusum.k_allowance", 0.15),
            "cusum_h": thresholds_loader.get("cusum.h_decision_threshold", 5.0),
            "mnf_window": f"{thresholds_loader.get('mnf.night_window_start', '01:00')}–{thresholds_loader.get('mnf.night_window_end', '05:00')}",
        },
        # The guard can veto a fused alarm, so the published formula would be
        # incomplete without it — mass_balance, cusum and mnf all read the same
        # residual, and their agreement alone cannot prove that reading is real.
        "plausibility_guard": {
            "enabled": bool(thresholds_loader.get("plausibility.enabled", True)),
            "current_ma_per_leak_lpm": thresholds_loader.get("plausibility.current_ma_per_leak_lpm", 35.0),
            "acoustic_min_residual_lpm": thresholds_loader.get("plausibility.acoustic_min_residual_lpm", 1.0),
            "margin": thresholds_loader.get("plausibility.margin", 2.0),
            "min_residual_lpm": thresholds_loader.get("plausibility.min_residual_lpm", 0.75),
            "rule": (
                "A flow-channel alarm is withheld when an independent channel that "
                "should have resolved a leak of the claimed size reports nothing, and "
                "no channel corroborates. Suppression is reported as an instrument fault."
            ),
        },
    }


@app.get("/api/status")
def system_status():
    """Real component status for the dashboard's top row. Every field is
    observed, not asserted — an unreachable component reports as down."""
    last = _ingestor.latest_telemetry

    mongo_ok, record_count, mongo_error = False, None, None
    try:
        from backend.repositories.db import get_db
        db = get_db()
        db.command("ping")
        mongo_ok = True
        record_count = db.telemetry.estimated_document_count()
    except Exception as e:
        mongo_error = str(e)[:120]

    mqtt_ok = _live_source.is_running

    # The rig is considered online only if live telemetry arrived recently.
    rig_online, rig_last_seen = False, None
    if _mode == MODE_LIVE and _ingestor.latest_telemetry:
        rig_last_seen = _ingestor.latest_telemetry.get("ts")
        try:
            rig_online = (time.time() - float(rig_last_seen)) < 10
        except (TypeError, ValueError):
            rig_online = False

    return {
        "mode": _mode,
        "source": (_active_source().describe() if _active_source() else {"source": _mode, "running": False}),
        "rig": {
            "online": rig_online,
            "last_seen_ts": rig_last_seen,
            "detail": "receiving telemetry" if rig_online else (
                "no telemetry received" if _mode == MODE_LIVE else "not applicable in Mock Data Mode"),
        },
        "mqtt": {
            "connected": mqtt_ok,
            "detail": "subscribed to rig/telemetry" if mqtt_ok else "broker unreachable",
        },
        "mongodb": {
            "connected": mongo_ok,
            "telemetry_records": record_count,
            "detail": "connected" if mongo_ok else (mongo_error or "unreachable"),
        },
        "pipeline": {
            "receiving": last is not None,
            "detail": "processing samples" if last is not None else "no samples yet",
        },
        "healthy": mongo_ok and (mqtt_ok or _mode == MODE_MOCK) and last is not None,
        "timestamp": int(time.time()),
    }


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
