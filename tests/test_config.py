import pytest

from fleetflow.config import ConfigError, SimConfig


def test_defaults_are_valid():
    SimConfig()


@pytest.mark.parametrize("kwargs", [
    {"num_robots": 0},
    {"num_robots": True},
    {"num_robots": 2.5},
    {"strategy": "random"},
    {"arrival_rate": -1},
    {"arrival_rate": float("nan")},
    {"service_ticks": -1},
    {"battery_capacity": 0},
    {"battery_reserve": 100.0},
    {"charge_rate": 0},
    {"stuck_threshold": 0},
    {"plan_slack": 0},
])
def test_invalid_settings_are_rejected(kwargs):
    with pytest.raises(ConfigError):
        SimConfig(**kwargs)


def test_all_problems_are_reported_together():
    with pytest.raises(ConfigError) as info:
        SimConfig(num_robots=0, strategy="nope")
    assert "num_robots" in str(info.value) and "strategy" in str(info.value)
