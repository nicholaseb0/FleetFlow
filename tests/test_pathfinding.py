import random

import pytest

from fleetflow.pathfinding import find_evasion_cell, plan_path
from fleetflow.reservation import ReservationTable


def position(path, t):
    return path[min(t, len(path) - 1)]  # robots stay on their last cell


def assert_no_conflicts(plans):
    ids = list(plans)
    horizon = max(len(p) for p in plans.values()) + 1
    for t in range(horizon):
        cells = [position(plans[i], t) for i in ids]
        assert len(set(cells)) == len(cells), f"vertex conflict at t={t}: {cells}"
        if t == 0:
            continue
        prev = [position(plans[i], t - 1) for i in ids]
        for a in range(len(ids)):
            for b in range(a + 1, len(ids)):
                swapped = prev[a] == cells[b] and prev[b] == cells[a] and prev[a] != cells[a]
                assert not swapped, f"swap conflict at t={t} between robots {ids[a]} and {ids[b]}"


def assert_contiguous(warehouse, path):
    for a, b in zip(path, path[1:]):
        assert a == b or b in warehouse.neighbors(a), f"illegal step {a} -> {b}"


def test_unobstructed_path_is_shortest(small_map):
    path = plan_path(small_map, ReservationTable(), 0, (1, 1), (4, 3), start_t=0, horizon=30)
    assert path[0] == (1, 1) and path[-1] == (4, 3)
    assert len(path) - 1 == small_map.distance((1, 1), (4, 3))
    assert_contiguous(small_map, path)


def test_fails_fast_when_goal_is_occupied(small_map):
    table = ReservationTable()
    table.park(1, (4, 3), since=0)
    assert plan_path(small_map, table, 0, (1, 1), (4, 3), start_t=0, horizon=30) is None


def test_routes_around_parked_robot(small_map):
    table = ReservationTable()
    table.park(1, (3, 1), since=0)
    path = plan_path(small_map, table, 0, (1, 1), (4, 3), start_t=0, horizon=30)
    assert (3, 1) not in path
    assert len(path) - 1 == 7
    assert_contiguous(small_map, path)


def test_avoids_crossing_robot(small_map):
    table = ReservationTable()
    first = plan_path(small_map, table, 0, (3, 1), (3, 5), start_t=0, horizon=30)
    table.reserve_path(0, first, 0)
    second = plan_path(small_map, table, 1, (1, 5), (4, 1), start_t=0, horizon=30)
    assert second is not None and second[-1] == (4, 1)
    assert_contiguous(small_map, second)
    assert_no_conflicts({0: first, 1: second})


def test_sequential_planning_is_collision_free(default_map):
    rng = random.Random(7)
    cells = default_map.pickup_cells + default_map.stations
    for _ in range(5):
        chosen = rng.sample(cells, 12)
        starts, goals = chosen[:6], chosen[6:]
        table = ReservationTable()
        for rid, start in enumerate(starts):
            table.park(rid, start, since=0)
        plans = {}
        for rid, (start, goal) in enumerate(zip(starts, goals)):
            table.release(rid)
            path = plan_path(default_map, table, rid, start, goal, start_t=0, horizon=120)
            if path is None:
                table.park(rid, start, since=0)
                plans[rid] = [start]
            else:
                table.reserve_path(rid, path, 0)
                assert_contiguous(default_map, path)
                plans[rid] = path
        assert_no_conflicts(plans)
        reached = sum(plans[rid][-1] == goal for rid, goal in enumerate(goals))
        assert reached >= 4


def test_invalid_start_raises(small_map):
    with pytest.raises(ValueError):
        plan_path(small_map, ReservationTable(), 0, (0, 0), (4, 3), start_t=0, horizon=10)


def test_evasion_cell_is_nearby_parking_cell(small_map):
    cell = find_evasion_cell(small_map, ReservationTable(), 0, (3, 2), 0)
    assert cell in small_map.parking_cells
    assert cell != (3, 2)
    assert small_map.distance((3, 2), cell) == 1
