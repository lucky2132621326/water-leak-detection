"""Replay Runner

Streams a stored run's telemetry through the SAME DetectionPipeline used by
live MQTT ingestion, then scores it against that run's ground-truth leak
events (precision/recall/F1/latency — all computed here, not hardcoded).
This is what makes "replay mode" a real second data source rather than a
separately mocked implementation.
"""
from backend.repositories.telemetry_repository import TelemetryRepository
from backend.repositories.detection_repository import LeakEventRepository, DetectionRepository
from backend.pipeline import DetectionPipeline
from backend.response.response_builder import build_response
from backend.utils.logger import logger


class ReplayRunner:
    def __init__(self, telemetry_repo=None, leak_event_repo=None, detection_repo=None):
        self.telemetry_repo = telemetry_repo or TelemetryRepository()
        self.leak_event_repo = leak_event_repo or LeakEventRepository()
        self.detection_repo = detection_repo or DetectionRepository()

    def run(self, run_id: str, on_sample=None):
        telemetry_docs = self.telemetry_repo.get_by_run(run_id)
        ground_truth = self.leak_event_repo.get_for_run(run_id)

        if not telemetry_docs:
            logger.warning(f"[Replay] No telemetry found for run_id={run_id}")
            return {"run_id": run_id, "samples": 0, "metrics": None}

        pipeline = DetectionPipeline()
        tp = fp = fn = tn = 0
        detected_ts_by_event = {}

        for doc in telemetry_docs:
            flow = doc["flow"]
            power = doc["power"]
            actuators = doc.get("actuators", {})

            result = pipeline.process_sample(
                ts=doc["ts"],
                q_in=flow["q_in_lpm"],
                q_out=flow["q_out_lpm"],
                q_branch=flow.get("q_branch_lpm", 0.0),
                current_ma=power["current_ma"],
                voltage_v=power.get("voltage", 12.0),
                pump_on=actuators.get("pump1", True),
                servo_state_deg=actuators.get("servo_deg", 0),
                pressure_bar=doc.get("pressure_bar"),
                vibration=doc.get("vibration"), water_temp_c=(doc.get("temp") or {}).get("water_c"),
            )
            response = build_response(result)
            self.detection_repo.save_response(response, run_id=run_id)

            is_detected = response["is_alarm"]
            matching_event = next(
                (gt for gt in ground_truth if gt["start_ts"] <= doc["ts"] <= (gt.get("stop_ts") or doc["ts"] + 1)),
                None
            )

            if is_detected and matching_event:
                tp += 1
                key = str(matching_event["_id"])
                if key not in detected_ts_by_event:
                    detected_ts_by_event[key] = doc["ts"]
            elif is_detected and not matching_event:
                fp += 1
            elif not is_detected and matching_event:
                fn += 1
            else:
                tn += 1

            if on_sample:
                on_sample(response)

        precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

        latencies = [
            detected_ts_by_event[str(gt["_id"])] - gt["start_ts"]
            for gt in ground_truth
            if str(gt["_id"]) in detected_ts_by_event
        ]
        avg_latency_sec = round(sum(latencies) / len(latencies), 2) if latencies else None

        return {
            "run_id": run_id,
            "samples": len(telemetry_docs),
            "metrics": {
                "precision": round(precision, 3),
                "recall": round(recall, 3),
                "f1_score": round(f1, 3),
                "true_positives": tp,
                "false_positives": fp,
                "false_negatives": fn,
                "true_negatives": tn,
                "avg_latency_sec": avg_latency_sec,
            }
        }
