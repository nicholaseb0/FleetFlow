import random

import pytest

from fleetflow.tasks import TaskGenerator


def collect(generator, ticks):
    return [task for tick in range(ticks) for task in generator.generate(tick)]


def test_same_seed_gives_same_tasks(default_map):
    a = collect(TaskGenerator(default_map, 0.5, random.Random(3)), 200)
    b = collect(TaskGenerator(default_map, 0.5, random.Random(3)), 200)
    assert a  # non-empty
    assert [(t.pickup, t.dropoff, t.created_at) for t in a] == [(t.pickup, t.dropoff, t.created_at) for t in b]


def test_zero_rate_generates_nothing(default_map):
    assert collect(TaskGenerator(default_map, 0.0, random.Random(1)), 500) == []


def test_tasks_use_valid_cells_and_unique_ids(default_map):
    tasks = collect(TaskGenerator(default_map, 1.0, random.Random(2)), 300)
    assert all(t.pickup in default_map.pickup_cells for t in tasks)
    assert all(t.dropoff in default_map.stations for t in tasks)
    assert [t.id for t in tasks] == list(range(len(tasks)))


def test_average_rate_matches_parameter(default_map):
    ticks = 4000
    tasks = collect(TaskGenerator(default_map, 0.5, random.Random(4)), ticks)
    assert 0.45 <= len(tasks) / ticks <= 0.55


@pytest.mark.parametrize("rate", [-0.1, float("nan"), float("inf")])
def test_invalid_rate_rejected(default_map, rate):
    with pytest.raises(ValueError):
        TaskGenerator(default_map, rate, random.Random(0))
