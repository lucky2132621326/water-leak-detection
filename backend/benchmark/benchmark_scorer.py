"""Benchmark Scorer

Scores a stored run offline: streams its telemetry through the SAME
DetectionPipeline that live and mock ingestion use, then grades the result
against that run's logged ground-truth leak windows. Precision, recall, F1 and
latency are all computed here, never authored.

This is an analysis tool, not an operating mode. It runs on demand against
recorded data and does not feed the dashboard. Mock scenarios, which carry
known ground truth by construction, are its corpus.
"""
from backend.repositories.telemetry_repository import TelemetryRepository
from backend.repositories.detection_repository import LeakEventRepository, DetectionRepository
from backend.pipeline import DetectionPipeline
from backend.response.response_builder import build_response
from backend.benchmark.ground_truth import GroundTruthScorer
from backend.utils.logger import logger
from backend.validators.telemetry_validator import TelemetryValidator


class BenchmarkScorer:
    def __init__(self, telemetry_repo=None, leak_event_repo=None, detection_repo=None):
        self.telemetry_repo = telemetry_repo or TelemetryRepository()
        self.leak_event_repo = leak_event_repo or LeakEventRepository()
        self.detection_repo = detection_repo or DetectionRepository()

    def run(self, run_id: str, on_sample=None):
        telemetry_docs = self.telemetry_repo.get_by_run(run_id)
        ground_truth = self.leak_event_repo.get_for_run(run_id)

        if not telemetry_docs:
            logger.warning(f"[Benchmark] No telemetry found for run_id={run_id}")
            return {"run_id": run_id, "samples": 0, "metrics": None}

        pipeline = DetectionPipeline()
        scorer = GroundTruthScorer(ground_truth)

        for doc in telemetry_docs:
            dto, error = TelemetryValidator.normalize(doc)
            if dto is None:
                logger.warning(f"[Benchmark] skipped invalid telemetry: {error}")
                continue

            result = pipeline.process_sample(dto)
            response = build_response(result)
            self.detection_repo.save_response(response, run_id=run_id)

            scorer.observe(doc["ts"], response["is_alarm"])

            if on_sample:
                on_sample(response)

        metrics = scorer.summary()
        metrics["avg_latency_sec"] = metrics["detection_latency_sec"]

        return {
            "run_id": run_id,
            "samples": len(telemetry_docs),
            "metrics": metrics,
        }
