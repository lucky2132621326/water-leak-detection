"""Water Loss Calculator

Converts a leak rate in L/min into the time horizons humans reason about, plus
relatable physical equivalents. Pure arithmetic — no I/O, no database, so it is
trivially unit-testable and safe to call on every telemetry sample.
"""
from backend.config.config_loader import impact_loader

MINUTES_PER_HOUR = 60
HOURS_PER_DAY = 24
DAYS_PER_WEEK = 7
DAYS_PER_MONTH = 30  # billing-month convention, matches how utilities quote losses
DAYS_PER_YEAR = 365


class WaterLossCalculator:
    def __init__(self, equivalents: dict = None):
        eq = equivalents or impact_loader.get("equivalents", {}) or {}
        self.tank_litres = float(eq.get("tank_litres", 200))
        self.person_daily_litres = float(eq.get("person_daily_litres", 135))
        self.bucket_litres = float(eq.get("bucket_litres", 20))

    @staticmethod
    def litres_over(leak_rate_lpm: float, minutes: float) -> float:
        """Litres lost if `leak_rate_lpm` runs uninterrupted for `minutes`."""
        return max(0.0, float(leak_rate_lpm)) * float(minutes)

    def compute(self, leak_rate_lpm: float) -> dict:
        rate = max(0.0, float(leak_rate_lpm))

        per_hour = rate * MINUTES_PER_HOUR
        per_day = per_hour * HOURS_PER_DAY
        per_week = per_day * DAYS_PER_WEEK
        per_month = per_day * DAYS_PER_MONTH
        per_year = per_day * DAYS_PER_YEAR

        return {
            "leak_rate_lpm": round(rate, 3),
            "litres_per_hour": round(per_hour, 1),
            "litres_per_day": round(per_day, 1),
            "litres_per_week": round(per_week, 1),
            "litres_per_month": round(per_month, 1),
            "litres_per_year": round(per_year, 1),
            "equivalents": self.equivalents_for(per_month),
        }

    def equivalents_for(self, litres: float) -> dict:
        """Relatable framings for a raw litre figure (defaults to a month's loss).

        Reported as floats rounded to 1dp rather than ints so small leaks don't
        collapse to a misleading '0 tanks'.
        """
        litres = max(0.0, float(litres))
        return {
            "basis_litres": round(litres, 1),
            "water_tanks": round(litres / self.tank_litres, 1) if self.tank_litres else 0.0,
            "tank_size_litres": self.tank_litres,
            "people_daily_supply": round(litres / self.person_daily_litres, 1) if self.person_daily_litres else 0.0,
            "person_daily_litres": self.person_daily_litres,
            "buckets": round(litres / self.bucket_litres, 1) if self.bucket_litres else 0.0,
            "bucket_size_litres": self.bucket_litres,
        }
