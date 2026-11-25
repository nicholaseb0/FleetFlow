import pytest

from fleetflow.config import ConfigError, SimConfig
from fleetflow.scheduler import STRATEGIES
from fleetflow.simulation import Simulation
from fleetflow.tasks import Task


@pytest.mark.parametrize("strategy", sorted(STRATEGIES))
def test_run_is_collision_free_and_completes_tasks(default_map, strategy):
    sim = Simulation(default_map, SimConfig(num_robots=6, strategy=strategy, seed=11, arrival_rate=0.1))
    summary = sim.run(600)
    assert summary["collisions"] == 0
    assert summary["tasks_completed"] > 0
    for task in sim.completed:
        assert task.created_at <= task.assigned_at <= task.picked_at <= task.completed_at


def test_invariants_hold_every_tick(default_map):
    sim = Simulation(default_map, SimConfig(num_robots=8, seed=3, arrival_rate=0.2))
    for _ in range(400):
        sim.step()
        positions = [r.position for r in sim.robots]
        assert len(set(positions)) == len(positions)
        assert all(default_map.is_walkable(p) for p in positions)
        assert all(0.0 <= r.battery <= r.capacity for r in sim.robots)
    assert sim.metrics.collisions == 0


def test_same_seed_is_deterministic(default_map):
    config = SimConfig(num_robots=5, seed=99)
    a = Simulation(default_map, config).run(400)
    b = Simulation(default_map, config).run(400)
    a.pop("avg_plan_ms")  # wall-clock time, legitimately varies
    b.pop("avg_plan_ms")
    assert a == b


def test_strategies_see_identical_task_streams(default_map):
    fifo = Simulation(default_map, SimConfig(strategy="fifo", seed=8)).run(300)
    greedy = Simulation(default_map, SimConfig(strategy="greedy", seed=8)).run(300)
    assert fifo["tasks_created"] == greedy["tasks_created"]


def test_all_tasks_finish_after_arrivals_stop(default_map):
    sim = Simulation(default_map, SimConfig(num_robots=6, seed=5, arrival_rate=0.15))
    sim.run(300)
    sim.generator.rate = 0.0
    summary = sim.run(2000)
    assert summary["tasks_pending"] == 0
    assert summary["tasks_completed"] == summary["tasks_created"]
    assert all(r.task is None for r in sim.robots)


def test_low_battery_robot_charges_before_dispatch(small_map):
    sim = Simulation(small_map, SimConfig(num_robots=1, arrival_rate=0.0))
    robot = sim.robots[0]
    robot.battery = 5.0
    task = Task(id=0, pickup=small_map.pickup_cells[0], dropoff=small_map.stations[0], created_at=0)
    sim.pending.append(task)
    sim.metrics.tasks_created += 1
    sim.step()
    assert robot.task is None
    assert robot.battery > 5.0
    sim.run(60)
    assert task.completed_at is not None


def test_too_many_robots_rejected(small_map):
    with pytest.raises(ConfigError, match="chargers"):
        Simulation(small_map, SimConfig(num_robots=3))


def test_negative_ticks_rejected(small_map):
    with pytest.raises(ValueError):
        Simulation(small_map, SimConfig(num_robots=1)).run(-1)
