import pytest

from fleetflow.grid import DIRECTIONS, SHELF, MapError, Warehouse


def test_default_map_loads(default_map):
    assert (default_map.width, default_map.height) == (24, 11)
    assert len(default_map.chargers) == 8
    assert len(default_map.stations) == 3
    for row, col in default_map.pickup_cells:
        assert default_map.is_walkable((row, col))
        around = [(row + dr, col + dc) for dr, dc in DIRECTIONS]
        assert any(default_map.in_bounds(c) and default_map.char_at(c) == SHELF for c in around)


def test_small_map_points_of_interest(small_map):
    assert small_map.chargers == [(1, 1), (1, 3)]
    assert small_map.stations == [(4, 3)]
    assert small_map.pickup_cells == [(1, 2), (2, 1), (2, 4), (3, 2), (3, 3)]
    assert not set(small_map.parking_cells) & set(small_map.pickup_cells)


def test_distances(small_map):
    assert small_map.distance((1, 1), (4, 3)) == 5
    assert small_map.distance((4, 3), (1, 1)) == 5
    assert small_map.distance((3, 3), (3, 3)) == 0


def test_neighbors_exclude_blocked_cells(small_map):
    assert set(small_map.neighbors((2, 1))) == {(1, 1), (3, 1)}  # (2,2) is a shelf


@pytest.mark.parametrize("text, message", [
    ("", "empty"),
    ("#C#\n#D\n", "rectangular"),
    ("#CX#\n#DS.\n", "invalid"),
    ("#..#\n#DS.\n", "charger"),
    ("#C.#\n#.S.\n", "drop station"),
    ("######\n#C#.D#\n#.#S.#\n######\n", "unreachable"),
])
def test_invalid_maps_are_rejected(text, message):
    with pytest.raises(MapError, match=message):
        Warehouse.from_string(text)


def test_missing_file_is_reported(tmp_path):
    with pytest.raises(MapError, match="not found"):
        Warehouse.from_file(tmp_path / "nope.txt")
