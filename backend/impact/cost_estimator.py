"""Cost Estimator

Applies a volumetric water tariff to the litre figures from WaterLossCalculator.
Tariffs are quoted per kilolitre (1000 L), which is how municipal slabs are
actually published, so the conversion lives in one place here.
"""
from backend.config.config_loader import impact_loader

LITRES_PER_KILOLITRE = 1000.0


class CostEstimator:
    def __init__(self, rate_per_kilolitre: float = None, currency_symbol: str = None):
        self.rate_per_kilolitre = float(
            rate_per_kilolitre
            if rate_per_kilolitre is not None
            else impact_loader.get("tariff.rate_per_kilolitre", 20.0)
        )
        self.currency_symbol = currency_symbol or impact_loader.get("tariff.currency_symbol", "₹")

    def cost_of(self, litres: float) -> float:
        """Cost of losing `litres` at the configured tariff."""
        return (max(0.0, float(litres)) / LITRES_PER_KILOLITRE) * self.rate_per_kilolitre

    def compute(self, water_loss: dict) -> dict:
        """Takes a WaterLossCalculator.compute() dict, returns the matching costs."""
        return {
            "currency_symbol": self.currency_symbol,
            "rate_per_kilolitre": round(self.rate_per_kilolitre, 2),
            "cost_per_hour": round(self.cost_of(water_loss["litres_per_hour"]), 2),
            "cost_per_day": round(self.cost_of(water_loss["litres_per_day"]), 2),
            "cost_per_week": round(self.cost_of(water_loss["litres_per_week"]), 2),
            "cost_per_month": round(self.cost_of(water_loss["litres_per_month"]), 2),
            "cost_per_year": round(self.cost_of(water_loss["litres_per_year"]), 2),
        }
