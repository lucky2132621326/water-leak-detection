"""Impact Service — the single composition point for impact analysis.

Everything downstream (the API's /api/impact routes, the alert records, the
work-order text, the printable experiment report) calls this rather than
assembling the four calculators itself, so a leak's stated severity and cost
can never disagree between two surfaces.
"""
from backend.impact.water_loss import WaterLossCalculator
from backend.impact.cost_estimator import CostEstimator
from backend.impact.severity import SeverityClassifier
from backend.impact.progression import ProgressionSimulator

_DISCLAIMER = (
    "Impact figures are indicative projections derived from the estimated leak "
    "rate and the configured water tariff. Field verification is required before "
    "any repair action."
)


class ImpactService:
    def __init__(self, tariff_per_kl: float = None, currency_symbol: str = None):
        self.calculator = WaterLossCalculator()
        self.estimator = CostEstimator(rate_per_kilolitre=tariff_per_kl, currency_symbol=currency_symbol)
        self.classifier = SeverityClassifier()
        self.simulator = ProgressionSimulator(self.calculator, self.estimator)

    def analyze(self, leak_rate_lpm: float, repair_delay_days: float = None) -> dict:
        rate = max(0.0, float(leak_rate_lpm or 0.0))

        water_loss = self.calculator.compute(rate)
        cost = self.estimator.compute(water_loss)
        severity = self.classifier.classify(rate)
        recommendation = self.classifier.recommend(rate, severity["label"])
        progression = self.simulator.simulate(rate, repair_delay_days)

        return {
            "leak_rate_lpm": water_loss["leak_rate_lpm"],
            "water_loss": water_loss,
            "cost": cost,
            "severity": severity,
            "recommendation": recommendation,
            "progression": progression,
            "disclaimer": _DISCLAIMER,
        }

    def summarize(self, leak_rate_lpm: float) -> dict:
        """Compact form for embedding in an alert row or a detection response —
        the same numbers as analyze(), without the full progression timeline."""
        analysis = self.analyze(leak_rate_lpm)
        return {
            "leak_rate_lpm": analysis["leak_rate_lpm"],
            "litres_per_day": analysis["water_loss"]["litres_per_day"],
            "litres_per_month": analysis["water_loss"]["litres_per_month"],
            "cost_per_day": analysis["cost"]["cost_per_day"],
            "cost_per_month": analysis["cost"]["cost_per_month"],
            "cost_per_year": analysis["cost"]["cost_per_year"],
            "currency_symbol": analysis["cost"]["currency_symbol"],
            "severity": analysis["severity"]["label"],
            "severity_color": analysis["severity"]["color"],
            "urgency": analysis["recommendation"]["urgency"],
        }


# Module-level default instance: impact analysis is stateless and config-driven,
# so there's no reason for every caller to build its own.
_default_service = None


def _service() -> ImpactService:
    global _default_service
    if _default_service is None:
        _default_service = ImpactService()
    return _default_service


def analyze_impact(leak_rate_lpm: float, repair_delay_days: float = None, tariff_per_kl: float = None) -> dict:
    """Convenience wrapper. A custom tariff (from the interactive simulator)
    builds a one-off service rather than mutating the shared default."""
    if tariff_per_kl is not None:
        return ImpactService(tariff_per_kl=tariff_per_kl).analyze(leak_rate_lpm, repair_delay_days)
    return _service().analyze(leak_rate_lpm, repair_delay_days)


def summarize_impact(leak_rate_lpm: float) -> dict:
    return _service().summarize(leak_rate_lpm)
