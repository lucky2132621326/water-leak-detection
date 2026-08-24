"""Mock Data Mode source.

Streams a generated scenario into the shared TelemetryIngestor. It is a
transport adapter in exactly the same sense as the MQTT source — it produces
wire-format payloads and hands them over. It performs no evaluation, so mock
and live data cannot take different detection paths.

Supports two execution speeds:

  * **streaming** (default) — one sample per second, optionally accelerated, so
    the dashboard animates as it would with a real rig.
  * **batch** — the whole scenario evaluated as fast as possible, for tests and
    scoring. A 300-sample scenario completes in milliseconds instead of five
    minutes.
"""
import threading
import time

from backend.ingestion.telemetry_source import TelemetrySource
from backend.mock.generator import MockTelemetryGenerator
from backend.mock.leak_control import MockLeakControl
from backend.mock.scenarios import ScenarioSpec
from backend.repositories.detection_repository import LeakEventRepository
from backend.repositories.db import get_db
from backend.utils.logger import logger


class MockTelemetrySource(TelemetrySource):
    name = "mock"

    def __init__(self, scenario: ScenarioSpec, speed: float = 4.0, loop: bool = True,
                 run_id: str = None, persist_ground_truth: bool = True,
                 realtime: bool = False):
        self.scenario = scenario
        self.speed = max(0.1, float(speed))
        self.loop = loop
        self.run_id = run_id
        self.persist_ground_truth = persist_ground_truth
        # Interactive runs stamp wall-clock time so timestamps advance
        # monotonically instead of resetting each loop — a looping past window
        # would make the alert service merge every cycle into one incident.
        self.realtime = realtime

        self.generator = MockTelemetryGenerator(scenario)
        # Operator's live leak intent. Read on every generated sample, so a
        # change takes effect on the next telemetry tick.
        self.control = MockLeakControl()
        self._thread = None
        self._stop = threading.Event()
        self._running = False
        self._cycle = 0

    @property
    def is_running(self) -> bool:
        return self._running

    # --- streaming --------------------------------------------------------
    def start(self, ingestor) -> None:
        self.stop()
        self._stop = threading.Event()
        self._running = True
        if self.persist_ground_truth and self.run_id:
            self._write_run_metadata()
        self._thread = threading.Thread(target=self._play, args=(ingestor,), daemon=True)
        self._thread.start()
        logger.info(
            f"[MockSource] streaming '{self.scenario.id}' "
            f"({self.scenario.duration_sec}s @ {self.speed}x, loop={self.loop})"
        )

    def _play(self, ingestor):
        while not self._stop.is_set():
            # A fresh generator each cycle keeps the RNG stream deterministic,
            # so cycle N is identical to cycle 1 rather than drifting.
            generator = MockTelemetryGenerator(self.scenario)
            t = 0.0
            while t <= self.scenario.duration_sec:
                if self._stop.is_set():
                    self._running = False
                    return
                # Re-read the override every sample rather than once per cycle,
                # which is what makes the leak controllable mid-stream.
                payload = generator.sample_at(
                    t, leak_override=self.control.snapshot(),
                    ts_override=time.time() if self.realtime else None)
                ingestor.ingest(payload, run_id=self.run_id)
                time.sleep(1.0 / self.speed)
                t += 1.0
            self._cycle += 1
            if not self.loop:
                break
        self._running = False

    def stop(self) -> None:
        if self._thread and self._thread.is_alive():
            self._stop.set()
            self._thread.join(timeout=3)
        self._running = False

    # --- batch ------------------------------------------------------------
    def run_batch(self, ingestor) -> dict:
        """Evaluate the whole scenario immediately and score it against its own
        ground truth. This is the benchmark path — no sleeping, no looping."""
        ingestor.reset()
        generator = MockTelemetryGenerator(self.scenario)
        if self.persist_ground_truth and self.run_id:
            self._write_run_metadata()
            self._write_ground_truth(generator)

        tp = fp = fn = tn = 0
        first_detection_offset = None
        samples = 0

        for offset, payload in enumerate(generator.stream()):
            response = ingestor.ingest(payload, run_id=self.run_id)
            samples += 1
            if response is None:
                continue  # rejected payload — counts as neither
            detected = bool(response["is_alarm"])
            # Ground truth belongs to the declarative scenario, not the sensor
            # packet. The rig has no leak solenoid and the telemetry contract
            # intentionally removed `solenoid_state`; reading that retired
            # field here made every dashboard batch score fail with HTTP 500.
            truth = self.scenario.is_leaking_at(float(offset))
            if detected and truth:
                tp += 1
                if first_detection_offset is None:
                    onset = min((l.start_sec for l in self.scenario.leaks), default=0)
                    first_detection_offset = max(0.0, offset - onset)
            elif detected and not truth:
                fp += 1
            elif truth:
                fn += 1
            else:
                tn += 1

        precision = tp / (tp + fp) if (tp + fp) else (1.0 if tp else None)
        recall = tp / (tp + fn) if (tp + fn) else None
        f1 = (2 * precision * recall / (precision + recall)) if (precision and recall) else None

        result = {
            "scenario_id": self.scenario.id,
            "scenario_name": self.scenario.name,
            "run_id": self.run_id,
            "samples": samples,
            "metrics": {
                "true_positives": tp, "false_positives": fp,
                "false_negatives": fn, "true_negatives": tn,
                "precision": round(precision, 4) if precision is not None else None,
                "recall": round(recall, 4) if recall is not None else None,
                "f1_score": round(f1, 4) if f1 is not None else None,
                "detection_latency_sec": first_detection_offset,
            },
            "expected": {
                "expect_detection": self.scenario.expect_detection,
                "expect_zone": self.scenario.expect_zone,
            },
        }
        result["verdict"] = self._verdict(result)
        logger.info(f"[MockSource] batch '{self.scenario.id}': {result['verdict']} {result['metrics']}")
        return result

    def _verdict(self, result: dict) -> str:
        m = result["metrics"]
        if self.scenario.expect_detection:
            if m["true_positives"] == 0:
                return "FAIL — leak was never detected"
            if m["recall"] is not None and m["recall"] < 0.5:
                return f"WEAK — detected, but recall {m['recall']:.0%}"
            return "PASS"
        # Clean scenarios: any alarm at all is a false positive.
        if m["false_positives"] > 0:
            return f"FAIL — {m['false_positives']} false positive sample(s) on a clean run"
        return "PASS"

    # --- persistence ------------------------------------------------------
    def _write_run_metadata(self):
        db = get_db()
        db.experiment_runs.delete_many({"run_id": self.run_id})
        db.experiment_runs.insert_one({
            "run_id": self.run_id,
            "operator": "mock",
            "date": time.strftime("%Y-%m-%d"),
            "location": self.scenario.expect_zone or "Main_Trunk",
            "leak_size_lpm": max((l.rate_lpm for l in self.scenario.leaks), default=0.0),
            "pump_mode": "Constant 12V",
            "notes": self.scenario.description,
            "scenario_id": self.scenario.id,
            # The tag that keeps synthetic runs out of operational KPIs.
            "source": "mock",
            "status": "COMPLETED",
        })

    def _write_ground_truth(self, generator: MockTelemetryGenerator):
        db = get_db()
        db.leak_events.delete_many({"run_id": self.run_id})
        db.telemetry.delete_many({"run_id": self.run_id})
        db.detections.delete_many({"run_id": self.run_id})
        events = generator.ground_truth_events()
        for e in events:
            db.leak_events.insert_one({**e, "run_id": self.run_id, "source": "mock"})

    def describe(self) -> dict:
        return {
            "source": self.name,
            "running": self.is_running,
            "scenario": self.scenario.summary(),
            "speed": self.speed,
            "loop": self.loop,
            "run_id": self.run_id,
            "cycles_completed": self._cycle,
            "leak_control": self.control.snapshot(),
        }
