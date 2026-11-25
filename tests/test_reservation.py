import pytest

from fleetflow.reservation import ReservationConflict, ReservationTable


def test_vertex_reservation_blocks_other_robots_only():
    table = ReservationTable()
    table.reserve_path(0, [(0, 0), (0, 1), (0, 2)], start_t=5)
    assert not table.is_free((0, 1), 6, robot_id=1)
    assert table.is_free((0, 1), 6, robot_id=0)
    assert table.is_free((0, 1), 7, robot_id=1)


def test_final_cell_is_parked_indefinitely():
    table = ReservationTable()
    table.reserve_path(0, [(0, 0), (0, 1), (0, 2)], start_t=5)
    assert table.parked_by((0, 2)) == 0
    assert table.is_free((0, 2), 6, robot_id=1)       # before arrival
    assert not table.is_free((0, 2), 100, robot_id=1)  # after arrival, forever
    assert not table.can_park((0, 2), 50, robot_id=1)


def test_head_on_swap_is_detected():
    table = ReservationTable()
    table.reserve_path(0, [(0, 0), (0, 1)], start_t=0)
    assert not table.edge_free((0, 1), (0, 0), 0, robot_id=1)
    assert table.edge_free((0, 1), (0, 0), 1, robot_id=1)


def test_cannot_park_where_another_robot_will_pass():
    table = ReservationTable()
    table.reserve_path(0, [(0, 0), (0, 1), (0, 2), (0, 3)], start_t=0)
    assert not table.can_park((0, 1), 0, robot_id=1)
    assert not table.can_park((0, 1), 1, robot_id=1)
    assert table.can_park((0, 1), 2, robot_id=1)


def test_conflicting_reservation_raises_and_changes_nothing():
    table = ReservationTable()
    table.reserve_path(0, [(0, 0), (0, 1)], start_t=0)
    with pytest.raises(ReservationConflict):
        table.reserve_path(1, [(0, 2), (0, 1)], start_t=0)
    assert table.parked_by((0, 1)) == 0
    assert table.is_free((0, 2), 0, robot_id=2)


def test_release_frees_everything():
    table = ReservationTable()
    table.reserve_path(0, [(0, 0), (0, 1), (0, 2)], start_t=0)
    table.release(0)
    assert table.is_free((0, 1), 1, robot_id=1)
    assert table.parked_by((0, 2)) is None
    assert table.can_park((0, 1), 0, robot_id=1)


def test_prune_drops_only_past_claims():
    table = ReservationTable()
    table.reserve_path(0, [(0, 0), (0, 1), (0, 2), (0, 3)], start_t=0)
    table.prune(2)
    assert table.is_free((0, 1), 1, robot_id=1)
    assert not table.is_free((0, 2), 2, robot_id=1)
    assert table.parked_by((0, 3)) == 0
