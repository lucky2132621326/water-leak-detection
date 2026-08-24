from backend.mock.mock_source import MockTelemetrySource
from backend.mock.scenarios import get_scenario


class AlwaysClearIngestor:
    def reset(self):
        pass

    def ingest(self, payload, run_id=None):
        return {"is_alarm": False}


def test_batch_ground_truth_comes_from_scenario_not_removed_solenoid_field():
    scenario = get_scenario("small_leak")
    source = MockTelemetrySource(scenario, persist_ground_truth=False)

    result = source.run_batch(AlwaysClearIngestor())

    assert result["samples"] == scenario.duration_sec + 1
    assert result["metrics"]["false_negatives"] > 0


def test_manual_control_is_not_a_scoreable_benchmark():
    assert get_scenario("manual_control").summary()["scoreable"] is False
    assert get_scenario("small_leak").summary()["scoreable"] is True
