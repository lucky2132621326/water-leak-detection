"""Leak Severity Classification & Repair-Urgency Recommendation

Operators triage by category, not by raw L/min. Bands come from
backend/config/impact.yaml so a utility can retune them without a code change.

The recommendation output is deliberately a *scheduling* recommendation
("repair within 7 days") — never a valve or pump instruction, per the project's
guardrail that this system does not issue operational control actions.
"""
from backend.config.config_loader import impact_loader

# Presentation hints kept alongside the labels so the dashboard, the work-order
# text, and the printable report all agree on what MAJOR looks like.
SEVERITY_STYLE = {
    "NONE":     {"color": "slate",  "emoji": "⚪", "rank": 0},
    "MINOR":    {"color": "emerald", "emoji": "🟢", "rank": 1},
    "MODERATE": {"color": "amber",  "emoji": "🟡", "rank": 2},
    "MAJOR":    {"color": "orange", "emoji": "🟠", "rank": 3},
    "CRITICAL": {"color": "rose",   "emoji": "🔴", "rank": 4},
}


class SeverityClassifier:
    def __init__(self, bands=None, critical_label=None, recommendation=None):
        self.bands = sorted(
            bands if bands is not None else (impact_loader.get("severity_bands") or []),
            key=lambda b: b["max_lpm"],
        )
        self.critical_label = critical_label or impact_loader.get("critical_label", "CRITICAL")
        self.recommendation_thresholds = recommendation or impact_loader.get("recommendation", {}) or {}

    def classify(self, leak_rate_lpm: float) -> dict:
        rate = max(0.0, float(leak_rate_lpm))

        if rate <= 0.0:
            label = "NONE"
        else:
            label = self.critical_label
            for band in self.bands:
                if rate < float(band["max_lpm"]):
                    label = band["label"]
                    break

        style = SEVERITY_STYLE.get(label, SEVERITY_STYLE["MINOR"])
        return {
            "label": label,
            "color": style["color"],
            "emoji": style["emoji"],
            "rank": style["rank"],
            "leak_rate_lpm": round(rate, 3),
            "band_description": self.describe_bands(),
        }

    def describe_bands(self):
        """Human-readable band table, so the UI can show operators why a leak
        landed in the category it did instead of asking them to trust a label."""
        out = []
        lower = 0.0
        for band in self.bands:
            out.append({"label": band["label"], "min_lpm": round(lower, 3), "max_lpm": float(band["max_lpm"])})
            lower = float(band["max_lpm"])
        out.append({"label": self.critical_label, "min_lpm": round(lower, 3), "max_lpm": None})
        return out

    def recommend(self, leak_rate_lpm: float, severity_label: str = None) -> dict:
        """Repair-urgency advice. Scheduling guidance only — no control actions."""
        rate = max(0.0, float(leak_rate_lpm))
        label = severity_label or self.classify(rate)["label"]

        immediate = float(self.recommendation_thresholds.get("immediate_lpm", 1.0))
        urgent = float(self.recommendation_thresholds.get("urgent_lpm", 0.5))
        scheduled = float(self.recommendation_thresholds.get("scheduled_lpm", 0.2))

        if rate <= 0.0:
            return {
                "urgency": "NONE",
                "headline": "No active loss detected",
                "action": "Continue routine monitoring.",
                "repair_within_days": None,
            }
        if rate >= immediate:
            return {
                "urgency": "IMMEDIATE",
                "headline": "Critical leak — immediate repair recommended",
                "action": "Dispatch a crew for field verification today. Losses at this rate compound quickly.",
                "repair_within_days": 1,
            }
        if rate >= urgent:
            return {
                "urgency": "URGENT",
                "headline": "Repair within 7 days",
                "action": "Schedule field verification this week before monthly losses accumulate.",
                "repair_within_days": 7,
            }
        if rate >= scheduled:
            return {
                "urgency": "SCHEDULED",
                "headline": "Repair within 30 days",
                "action": "Add to the next planned maintenance window and keep the zone under watch.",
                "repair_within_days": 30,
            }
        return {
            "urgency": "MONITOR",
            "headline": "Monitor — below actionable loss threshold",
            "action": "Log the observation and re-evaluate if the residual trends upward.",
            "repair_within_days": 90,
        }
