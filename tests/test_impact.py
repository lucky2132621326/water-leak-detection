"""Impact engine unit tests.

Pins the arithmetic that every operator-facing number depends on. If these
drift, the dashboard, the alert rows and the printable report all start quoting
figures that don't reconcile with each other.
"""
import os
import sys
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from backend.impact.water_loss import WaterLossCalculator
from backend.impact.cost_estimator import CostEstimator
from backend.impact.severity import SeverityClassifier
from backend.impact.progression import ProgressionSimulator
from backend.impact.impact_service import ImpactService


class TestWaterLoss(unittest.TestCase):
    def setUp(self):
        self.calc = WaterLossCalculator()

    def test_known_leak_rate(self):
        # 0.62 L/min is the worked example carried through the docs and UI.
        r = self.calc.compute(0.62)
        self.assertAlmostEqual(r["litres_per_hour"], 37.2, places=1)
        self.assertAlmostEqual(r["litres_per_day"], 892.8, places=1)
        self.assertAlmostEqual(r["litres_per_month"], 26784.0, places=1)

    def test_horizons_are_consistent(self):
        r = self.calc.compute(1.0)
        self.assertAlmostEqual(r["litres_per_day"], r["litres_per_hour"] * 24, places=1)
        self.assertAlmostEqual(r["litres_per_week"], r["litres_per_day"] * 7, places=1)
        self.assertAlmostEqual(r["litres_per_month"], r["litres_per_day"] * 30, places=1)
        self.assertAlmostEqual(r["litres_per_year"], r["litres_per_day"] * 365, places=1)

    def test_negative_rate_clamps_to_zero(self):
        # A negative residual means more water left the zone than entered it —
        # a sensor artefact, not a leak. It must never become negative "loss".
        r = self.calc.compute(-2.0)
        self.assertEqual(r["leak_rate_lpm"], 0.0)
        self.assertEqual(r["litres_per_day"], 0.0)

    def test_equivalents(self):
        eq = self.calc.equivalents_for(21600.0)
        self.assertAlmostEqual(eq["water_tanks"], 108.0, places=1)   # 200 L tanks
        self.assertAlmostEqual(eq["buckets"], 1080.0, places=1)      # 20 L buckets


class TestCostEstimator(unittest.TestCase):
    def test_default_currency_symbol_is_utf8(self):
        self.assertEqual(CostEstimator().currency_symbol, "₹")

    def test_tariff_applied_per_kilolitre(self):
        est = CostEstimator(rate_per_kilolitre=25.0)
        self.assertAlmostEqual(est.cost_of(1000.0), 25.0, places=2)
        self.assertAlmostEqual(est.cost_of(21600.0), 540.0, places=2)

    def test_full_breakdown(self):
        calc = WaterLossCalculator()
        est = CostEstimator(rate_per_kilolitre=25.0)
        cost = est.compute(calc.compute(0.5))
        self.assertAlmostEqual(cost["cost_per_month"], 540.0, places=2)
        self.assertAlmostEqual(cost["cost_per_year"], 6570.0, places=2)

    def test_zero_rate_costs_nothing(self):
        self.assertEqual(CostEstimator(rate_per_kilolitre=20.0).cost_of(0.0), 0.0)


class TestSeverityClassifier(unittest.TestCase):
    def setUp(self):
        self.clf = SeverityClassifier()

    def test_band_assignment(self):
        cases = [
            (0.0, "NONE"), (0.1, "MINOR"), (0.19, "MINOR"),
            (0.2, "MODERATE"), (0.49, "MODERATE"),
            (0.5, "MAJOR"), (0.73, "MAJOR"), (0.99, "MAJOR"),
            (1.0, "CRITICAL"), (5.0, "CRITICAL"),
        ]
        for rate, expected in cases:
            with self.subTest(rate=rate):
                self.assertEqual(self.clf.classify(rate)["label"], expected)

    def test_boundaries_are_exclusive_upper(self):
        # A band's max is the next band's floor — 0.2 must be MODERATE, not MINOR,
        # so no rate can fall into two bands.
        self.assertEqual(self.clf.classify(0.2)["label"], "MODERATE")
        self.assertEqual(self.clf.classify(0.5)["label"], "MAJOR")
        self.assertEqual(self.clf.classify(1.0)["label"], "CRITICAL")

    def test_recommendation_escalates_with_rate(self):
        self.assertEqual(self.clf.recommend(0.0)["urgency"], "NONE")
        self.assertEqual(self.clf.recommend(0.1)["urgency"], "MONITOR")
        self.assertEqual(self.clf.recommend(0.3)["urgency"], "SCHEDULED")
        self.assertEqual(self.clf.recommend(0.6)["urgency"], "URGENT")
        self.assertEqual(self.clf.recommend(1.5)["urgency"], "IMMEDIATE")

    def test_recommendation_never_issues_control_instructions(self):
        # Project guardrail: advise on scheduling, never on operating valves/pumps.
        banned = ("valve", "close the", "open the", "shut off", "pump off", "isolate")
        for rate in (0.1, 0.3, 0.6, 2.0):
            text = (self.clf.recommend(rate)["action"] + " " + self.clf.recommend(rate)["headline"]).lower()
            for word in banned:
                self.assertNotIn(word, text, f"control instruction '{word}' leaked at {rate} L/min")


class TestProgressionSimulator(unittest.TestCase):
    def setUp(self):
        self.sim = ProgressionSimulator(WaterLossCalculator(), CostEstimator(rate_per_kilolitre=25.0))

    def test_timeline_matches_worked_example(self):
        result = self.sim.simulate(0.5, repair_delay_days=30)
        by_label = {p["label"]: p for p in result["timeline"]}
        self.assertAlmostEqual(by_label["1 Day"]["litres"], 720.0, places=1)
        self.assertAlmostEqual(by_label["1 Week"]["litres"], 5040.0, places=1)
        self.assertAlmostEqual(by_label["1 Month"]["litres"], 21600.0, places=1)
        self.assertAlmostEqual(by_label["1 Year"]["litres"], 262800.0, places=1)
        self.assertAlmostEqual(by_label["1 Year"]["cost"], 6570.0, places=2)

    def test_timeline_is_monotonic(self):
        points = self.sim.simulate(0.8)["timeline"]
        litres = [p["litres"] for p in points]
        self.assertEqual(litres, sorted(litres))

    def test_fill_ratio_peaks_at_one(self):
        points = self.sim.simulate(1.2)["timeline"]
        self.assertAlmostEqual(max(p["fill_ratio"] for p in points), 1.0, places=3)
        self.assertTrue(all(0.0 <= p["fill_ratio"] <= 1.0 for p in points))

    def test_repair_delay_projection(self):
        at = self.sim.simulate(0.5, repair_delay_days=7)["at_repair_delay"]
        self.assertAlmostEqual(at["litres"], 5040.0, places=1)
        self.assertAlmostEqual(at["cost"], 126.0, places=2)

    def test_zero_leak_is_safe(self):
        result = self.sim.simulate(0.0)
        self.assertEqual(result["at_repair_delay"]["litres"], 0.0)
        self.assertTrue(all(p["fill_ratio"] == 0.0 for p in result["timeline"]))


class TestImpactService(unittest.TestCase):
    def test_analyze_is_internally_consistent(self):
        service = ImpactService(tariff_per_kl=20.0)
        a = service.analyze(0.62)
        self.assertEqual(a["severity"]["label"], "MAJOR")
        self.assertEqual(a["recommendation"]["urgency"], "URGENT")
        self.assertAlmostEqual(a["water_loss"]["litres_per_day"], 892.8, places=1)
        self.assertAlmostEqual(a["cost"]["cost_per_year"], 6517.44, places=2)

    def test_summary_matches_full_analysis(self):
        service = ImpactService(tariff_per_kl=20.0)
        full, brief = service.analyze(0.73), service.summarize(0.73)
        self.assertEqual(brief["severity"], full["severity"]["label"])
        self.assertEqual(brief["urgency"], full["recommendation"]["urgency"])
        self.assertEqual(brief["litres_per_day"], full["water_loss"]["litres_per_day"])
        self.assertEqual(brief["cost_per_year"], full["cost"]["cost_per_year"])

    def test_custom_tariff_scales_linearly(self):
        cheap = ImpactService(tariff_per_kl=10.0).analyze(1.0)["cost"]["cost_per_year"]
        dear = ImpactService(tariff_per_kl=20.0).analyze(1.0)["cost"]["cost_per_year"]
        self.assertAlmostEqual(dear, cheap * 2, places=2)


if __name__ == "__main__":
    unittest.main()
