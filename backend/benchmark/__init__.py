"""Offline benchmark scoring.

Scores a stored run's telemetry against its logged ground-truth leak windows by
replaying it through the production DetectionPipeline. This is an *analysis*
capability, not an operating mode — it powers Analytics, Reports and the
Benchmark tab.

It was previously called `ReplayRunner`, which conflated it with the old Replay
operating mode that streamed stored data to the dashboard. That mode is gone;
the scorer remains, and mock scenarios now supply its corpus.

`score_scenario` is the database-free counterpart: it grades a mock scenario in
memory, which is what makes the scenario pass rate assertable in CI rather than
recorded in a handoff note.
"""
from backend.benchmark.benchmark_scorer import BenchmarkScorer
from backend.benchmark.scenario_scorer import score_scenario, verdict

__all__ = ["BenchmarkScorer", "score_scenario", "verdict"]
