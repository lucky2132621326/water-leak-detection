"""Impact Analysis

Translates a detector's estimated leak rate (L/min) into the terms an operator
or municipality actually makes decisions in: litres lost per day/month/year,
rupees, a severity category, relatable volume equivalents, and a projection of
what continued inaction costs.

None of this issues valve or pump control instructions — it quantifies impact
and recommends a repair *urgency*, which is a scheduling decision, not an
operational control action.
"""
from backend.impact.water_loss import WaterLossCalculator
from backend.impact.cost_estimator import CostEstimator
from backend.impact.severity import SeverityClassifier
from backend.impact.progression import ProgressionSimulator
from backend.impact.impact_service import ImpactService, analyze_impact

__all__ = [
    "WaterLossCalculator",
    "CostEstimator",
    "SeverityClassifier",
    "ProgressionSimulator",
    "ImpactService",
    "analyze_impact",
]
