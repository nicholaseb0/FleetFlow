from fleetflow.robot import Robot
from fleetflow.scheduler import STRATEGIES, assign_fifo, assign_greedy, assign_nearest
from fleetflow.tasks import Task


def robot(i):
    return Robot(id=i, position=(0, i), charger=(0, i), capacity=100.0, battery=100.0)


def task(i, created):
    return Task(id=i, pickup=(1, i), dropoff=(2, 0), created_at=created)


def always(_r, _t):
    return True


COSTS = {(0, 0): 2, (1, 0): 3, (0, 1): 1, (1, 1): 10}


def cost(r, t):
    return COSTS[(r.id, t.id)]


def ids(pairs):
    return {(r.id, t.id) for r, t in pairs}


def test_fifo_gives_oldest_task_to_lowest_id():
    pairs = assign_fifo([robot(1), robot(0)], [task(10, created=5), task(11, created=2)], lambda r, t: 0, always)
    assert [(r.id, t.id) for r, t in pairs] == [(0, 11), (1, 10)]


def test_nearest_serves_tasks_in_age_order():
    pairs = assign_nearest([robot(0), robot(1)], [task(0, 0), task(1, 1)], cost, always)
    assert ids(pairs) == {(0, 0), (1, 1)}  # total cost 12


def test_greedy_takes_globally_cheapest_pairs():
    pairs = assign_greedy([robot(0), robot(1)], [task(0, 0), task(1, 1)], cost, always)
    assert ids(pairs) == {(0, 1), (1, 0)}
    assert sum(cost(r, t) for r, t in pairs) == 4


def test_ineligible_pairs_are_never_assigned():
    for strategy in STRATEGIES.values():
        pairs = strategy([robot(0), robot(1)], [task(0, 0), task(1, 1)], cost, lambda r, t: r.id != 0)
        assert len(pairs) == 1
        assert all(r.id != 0 for r, _ in pairs)


def test_one_task_per_robot():
    for strategy in STRATEGIES.values():
        pairs = strategy([robot(0)], [task(i, i) for i in range(5)], lambda r, t: t.id, always)
        assert len(pairs) == 1


def test_empty_inputs():
    for strategy in STRATEGIES.values():
        assert strategy([], [task(0, 0)], cost, always) == []
        assert strategy([robot(0)], [], cost, always) == []
