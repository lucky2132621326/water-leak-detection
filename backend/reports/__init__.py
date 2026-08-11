"""Automatic Experiment Reports

Builds a complete, self-contained write-up of a stored experiment run: metadata,
ground-truth leak events, detector performance scored by the real BenchmarkScorer,
plotted telemetry, quantified impact, and auto-generated conclusions.

Rendered as standalone HTML with print styling rather than through a PDF
library — the browser's "Save as PDF" produces the same artifact with no extra
dependency, and the HTML stays readable/diffable in the repo.
"""
from backend.reports.experiment_report import ExperimentReportGenerator

__all__ = ["ExperimentReportGenerator"]
