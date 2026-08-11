"""Benchmark Analytics — computed, never authored.

Replaces the previous roc_generator/latency_analysis/calibration_analysis
modules, which returned hardcoded numbers and were exposed by no route. Every
figure here is derived by replaying stored runs through the production
DetectionPipeline and scoring against logged ground truth, so the Analytics
screen can never disagree with the Benchmark screen.

If no runs have been recorded yet, this returns `has_data: False` rather than
placeholder values — an empty state is honest, invented metrics are not.
"""
from backend.repositories.db import get_db
from backend.benchmark.benchmark_scorer import BenchmarkScorer
from backend.detectors.detector_manager import DetectorManager
from backend.benchmark.ground_truth import matching_window, normalise_windows
from backend.fusion.fusion_engine import FusionEngine
from backend.models.telemetry import VibrationData
from backend.repositories.telemetry_repository import TelemetryRepository
from backend.repositories.detection_repository import LeakEventRepository
from backend.pipeline import DetectionPipeline
from backend.response.response_builder import build_response
from backend.utils.logger import logger


class BenchmarkAnalytics:
    def __init__(self, db=None):
        self.db = db if db is not None else get_db()
        self.telemetry_repo = TelemetryRepository(self.db)
        self.leak_event_repo = LeakEventRepository(self.db)

    # --- aggregate over every stored run --------------------------------
    def summary(self) -> dict:
        runs = list(self.db.experiment_runs.find({}, {"_id": 0}))
        if not runs:
            return {"has_data": False, "reason": "No experiment runs recorded yet.",
                    "run_count": 0, "runs": [], "overall": None, "per_method": [], "sensitivity": []}

        runner = BenchmarkScorer(self.telemetry_repo, self.leak_event_repo)
        scored, tp = [], 0
        fp = fn = tn = 0
        latencies = []

        for run in runs:
            result = runner.run(run["run_id"])
            m = result.get("metrics")
            if not m:
                continue
            tp += m["true_positives"]; fp += m["false_positives"]
            fn += m["false_negatives"]; tn += m["true_negatives"]
            if m.get("avg_latency_sec") is not None:
                latencies.append(m["avg_latency_sec"])
            scored.append({
                "run_id": run["run_id"],
                "leak_size_lpm": run.get("leak_size_lpm"),
                "location": run.get("location"),
                "samples": result.get("samples", 0),
                **m,
            })

        if not scored:
            return {"has_data": False, "reason": "Runs exist but none carry scoreable telemetry.",
                    "run_count": len(runs), "runs": [], "overall": None, "per_method": [], "sensitivity": []}

        overall = {
            "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
            "recall": round(tp / (tp + fn), 4) if (tp + fn) else None,
            "true_positives": tp, "false_positives": fp,
            "false_negatives": fn, "true_negatives": tn,
            "median_latency_sec": round(sorted(latencies)[len(latencies) // 2], 2) if latencies else None,
            "sample_count": tp + fp + fn + tn,
        }
        p, r = overall["precision"], overall["recall"]
        overall["f1_score"] = round(2 * p * r / (p + r), 4) if (p and r) else None

        return {
            "has_data": True,
            "run_count": len(scored),
            "runs": scored,
            "overall": overall,
            "per_method": self.per_method(),
            "sensitivity": self.sensitivity(scored),
            "basis": (
                f"Computed by replaying {len(scored)} stored run(s) through the production "
                "DetectionPipeline and scoring every sample against logged ground-truth leak "
                "windows. No value on this page is hardcoded."
            ),
        }

    # --- per-detector contribution --------------------------------------
    def per_method(self) -> list:
        """Scores each detector in isolation across all runs, so the fusion
        ensemble can be compared against its own inputs rather than against
        assumed baselines."""
        runs = list(self.db.experiment_runs.find({}, {"run_id": 1, "_id": 0}))
        methods = ["mass_balance", "current_signature", "cusum", "mnf", "acoustic"]
        stats = {m: {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "first_detect": []} for m in methods}
        stats["fusion"] = {"tp": 0, "fp": 0, "fn": 0, "tn": 0, "first_detect": []}

        for run in runs:
            run_id = run["run_id"]
            docs = self.telemetry_repo.get_by_run(run_id)
            windows = normalise_windows(self.leak_event_repo.get_for_run(run_id))
            if not docs:
                continue

            manager, fusion = DetectorManager(), FusionEngine()
            onset_seen = {k: None for k in stats}

            for doc in docs:
                flow, power = doc["flow"], doc["power"]
                results = manager.process_sample(
                    doc["ts"], flow["q_in_lpm"], flow["q_out_lpm"],
                    flow.get("q_branch_lpm", 0.0), power["current_ma"],
                    power.get("bus_v", 12.0), vibration=_vibration_of(doc),
                    pump_on=(doc.get("actuators") or {}).get("pump1", True))
                fused = fusion.fuse(results)

                in_leak = matching_window(doc["ts"], windows) is not None
                by_method = {d["method"]: d for d in results}
                by_method["fusion"] = {"is_alarm": fused["is_alarm"]}

                for name, s in stats.items():
                    alarm = bool(by_method.get(name, {}).get("is_alarm"))
                    if alarm and in_leak:
                        s["tp"] += 1
                        if onset_seen[name] is None:
                            gt = next(g for g in truth if g["start_ts"] <= doc["ts"] <= (g.get("stop_ts") or doc["ts"] + 1))
                            onset_seen[name] = doc["ts"] - gt["start_ts"]
                    elif alarm and not in_leak:
                        s["fp"] += 1
                    elif not alarm and in_leak:
                        s["fn"] += 1
                    else:
                        s["tn"] += 1

            for name, delay in onset_seen.items():
                if delay is not None:
                    stats[name]["first_detect"].append(delay)

        label = {
            "mass_balance": "Mass Balance Residual (3-Sigma)",
            "current_signature": "Motor Current Signature Analysis",
            "mnf": "Minimum Night Flow (MNF) Baseline",
            "cusum": "CUSUM Residual Cumulative Sum",
            "acoustic": "Acoustic (MPU6050 50-150 Hz)",
            "fusion": "Multi-Sensor Fusion (Weighted Ensemble)",
        }
        out = []
        for name, s in stats.items():
            tp, fp, fn = s["tp"], s["fp"], s["fn"]
            precision = round(tp / (tp + fp), 4) if (tp + fp) else None
            recall = round(tp / (tp + fn), 4) if (tp + fn) else None
            lat = s["first_detect"]
            out.append({
                "method": label[name],
                "key": name,
                "precision": precision,
                "recall": recall,
                "median_latency_sec": round(sorted(lat)[len(lat) // 2], 2) if lat else None,
                "false_positives": fp,
                "true_positives": tp,
                "false_negatives": fn,
            })
        return out

    @staticmethod
    def sensitivity(scored_runs: list) -> list:
        """Recall grouped by injected leak size — the honest way to state a
        detection floor instead of claiming uniform performance."""
        buckets = {}
        for r in scored_runs:
            size = r.get("leak_size_lpm")
            if size is None:
                continue
            b = buckets.setdefault(round(float(size), 2), {"tp": 0, "fn": 0, "fp": 0, "runs": 0})
            b["tp"] += r["true_positives"]; b["fn"] += r["false_negatives"]
            b["fp"] += r["false_positives"]; b["runs"] += 1

        out = []
        for size in sorted(buckets):
            b = buckets[size]
            out.append({
                "leak_size_lpm": size,
                "runs": b["runs"],
                "recall": round(b["tp"] / (b["tp"] + b["fn"]), 4) if (b["tp"] + b["fn"]) else None,
                "precision": round(b["tp"] / (b["tp"] + b["fp"]), 4) if (b["tp"] + b["fp"]) else None,
            })
        return out

    # --- ROC ------------------------------------------------------------
    def roc(self, run_id: str = None) -> dict:
        """Sweeps the fusion alarm threshold across stored samples to trace a
        real ROC curve. Each point is a threshold actually applied to real
        detector output, not a fitted curve."""
        query = {"run_id": run_id} if run_id else {}
        runs = list(self.db.experiment_runs.find(query, {"run_id": 1, "_id": 0}))
        scores = []

        for run in runs:
            rid = run["run_id"]
            docs = self.telemetry_repo.get_by_run(rid)
            windows = normalise_windows(self.leak_event_repo.get_for_run(rid))
            if not docs:
                continue
            manager, fusion = DetectorManager(), FusionEngine()
            for doc in docs:
                flow, power = doc["flow"], doc["power"]
                results = manager.process_sample(
                    doc["ts"], flow["q_in_lpm"], flow["q_out_lpm"],
                    flow.get("q_branch_lpm", 0.0), power["current_ma"],
                    power.get("bus_v", 12.0), vibration=_vibration_of(doc),
                    pump_on=(doc.get("actuators") or {}).get("pump1", True))
                fused = fusion.fuse(results)
                in_leak = matching_window(doc["ts"], windows) is not None
                scores.append((fused["fused_score"], in_leak))

        if not scores:
            return {"has_data": False, "points": [], "auc": None}

        positives = sum(1 for _, t in scores if t)
        negatives = len(scores) - positives
        if positives == 0 or negatives == 0:
            return {"has_data": False, "reason": "Need both leak and clean samples to plot a ROC curve.",
                    "points": [], "auc": None}

        points = []
        for i in range(21):
            thr = i / 20.0
            tp = sum(1 for s, t in scores if s >= thr and t)
            fp = sum(1 for s, t in scores if s >= thr and not t)
            points.append({"threshold": round(thr, 2),
                           "tpr": round(tp / positives, 4),
                           "fpr": round(fp / negatives, 4)})

        points.sort(key=lambda p: p["fpr"])
        auc = 0.0
        for a, b in zip(points, points[1:]):
            auc += (b["fpr"] - a["fpr"]) * (a["tpr"] + b["tpr"]) / 2.0

        logger.info(f"[Analytics] ROC computed over {len(scores)} samples, AUC={auc:.3f}")
        return {"has_data": True, "points": points, "auc": round(auc, 4),
                "sample_count": len(scores), "positive_samples": positives}


def _vibration_of(doc) -> VibrationData:
    """Rebuild the acoustic reading from a stored sample.

    A record written before the accelerometer existed has no `vibration` block.
    `has_accelerometer=False` makes the detector report inactive, so fusion
    renormalises around it — rather than scoring an old run as though the pipe
    had been listened to and found quiet.
    """
    vib = doc.get("vibration")
    if not vib:
        return VibrationData(has_accelerometer=False)
    return VibrationData(
        has_accelerometer=vib.get("band_mid") is not None,
        rms=float(vib.get("rms") or 0.0),
        band_low=float(vib.get("band_low") or 0.0),
        band_mid=float(vib.get("band_mid") or 0.0),
        band_high=float(vib.get("band_high") or 0.0),
        piezo_rms=vib.get("piezo_rms"),
        piezo_centroid_hz=vib.get("piezo_centroid_hz"),
    )
