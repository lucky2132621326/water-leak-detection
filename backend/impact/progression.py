"""Leak Progression Simulator — "what if nobody fixes this?"

Projects cumulative water and cost loss forward over a repair delay, and emits
milestone checkpoints (1 day / 1 week / 1 month / ...) suitable for a stepped
visual.

Assumes a constant leak rate for the whole horizon. That is a deliberate
simplification and is reported back in `assumptions` so the projection is never
mistaken for a physically-modelled forecast — real leaks typically worsen, so
this is a *lower* bound on loss.
"""
from backend.impact.water_loss import WaterLossCalculator, MINUTES_PER_HOUR, HOURS_PER_DAY
from backend.impact.cost_estimator import CostEstimator
from backend.config.config_loader import impact_loader

MINUTES_PER_DAY = MINUTES_PER_HOUR * HOURS_PER_DAY

# Fixed milestones always shown on the progression visual, regardless of the
# selected repair delay, so the shape of the curve is readable.
MILESTONES = [
    ("1 Day", 1),
    ("1 Week", 7),
    ("1 Month", 30),
    ("3 Months", 90),
    ("1 Year", 365),
]


class ProgressionSimulator:
    def __init__(self, calculator: WaterLossCalculator = None, estimator: CostEstimator = None):
        self.calculator = calculator or WaterLossCalculator()
        self.estimator = estimator or CostEstimator()

    @property
    def delay_options_days(self):
        return impact_loader.get("progression.delay_options_days", [1, 7, 30, 90, 365])

    @property
    def default_delay_days(self):
        return impact_loader.get("progression.default_delay_days", 30)

    def _point(self, label: str, days: float, rate_lpm: float, peak_litres: float) -> dict:
        litres = WaterLossCalculator.litres_over(rate_lpm, days * MINUTES_PER_DAY)
        return {
            "label": label,
            "days": days,
            "litres": round(litres, 1),
            "cost": round(self.estimator.cost_of(litres), 2),
            # Share of the largest point on the chart — drives the fill bar/tank
            # animation without the frontend re-deriving the scale.
            "fill_ratio": round(litres / peak_litres, 4) if peak_litres > 0 else 0.0,
        }

    def simulate(self, leak_rate_lpm: float, repair_delay_days: float = None) -> dict:
        rate = max(0.0, float(leak_rate_lpm))
        delay = float(repair_delay_days if repair_delay_days is not None else self.default_delay_days)
        delay = max(0.0, delay)

        peak_days = max([delay] + [d for _, d in MILESTONES])
        peak_litres = WaterLossCalculator.litres_over(rate, peak_days * MINUTES_PER_DAY)

        timeline = [self._point(label, days, rate, peak_litres) for label, days in MILESTONES]

        delay_litres = WaterLossCalculator.litres_over(rate, delay * MINUTES_PER_DAY)
        at_repair_delay = {
            "days": delay,
            "litres": round(delay_litres, 1),
            "cost": round(self.estimator.cost_of(delay_litres), 2),
            "equivalents": self.calculator.equivalents_for(delay_litres),
        }

        return {
            "leak_rate_lpm": round(rate, 3),
            "repair_delay_days": delay,
            "delay_options_days": self.delay_options_days,
            "timeline": timeline,
            "at_repair_delay": at_repair_delay,
            "currency_symbol": self.estimator.currency_symbol,
            "assumptions": (
                "Projection assumes the leak continues at a constant "
                f"{round(rate, 3)} L/min with no intervention. Real leaks usually "
                "worsen over time, so these figures are a conservative lower bound. "
                "Indicative only — field verification is required."
            ),
        }
