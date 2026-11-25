"""Warehouse map: loading, validation and static distance queries.

A map is plain text, one character per cell:

    #  wall            blocked
    S  shelf           blocked; floor cells next to a shelf are pickup points
    .  floor           walkable
    C  charger         walkable; each robot owns one, starts on it, charges there
    D  drop station    walkable; packages are delivered here
"""

from __future__ import annotations

import math
from collections import deque
from pathlib import Path
from typing import Iterator

Cell = tuple[int, int]  # (row, col)

WALL, SHELF, FLOOR, CHARGER, STATION = "#", "S", ".", "C", "D"
VALID_CHARS = frozenset({WALL, SHELF, FLOOR, CHARGER, STATION})
BLOCKED_CHARS = frozenset({WALL, SHELF})
DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))

DEFAULT_MAP = Path(__file__).parent / "maps" / "default.txt"


class MapError(ValueError):
    """Raised when a map is malformed or unusable."""


class Warehouse:
    """A static grid plus the points of interest derived from it."""

    def __init__(self, rows: list[str], name: str = "custom") -> None:
        self.name = name
        self._rows = _validate_shape(rows)
        self.height = len(self._rows)
        self.width = len(self._rows[0])

        # Neighbour lists are precomputed because A* asks for them constantly.
        self._neighbors: dict[Cell, tuple[Cell, ...]] = {
            cell: tuple(n for n in self._adjacent(cell) if self.is_walkable(n))
            for cell, char in self.cells()
            if char not in BLOCKED_CHARS
        }

        self.chargers = self._cells_with(CHARGER)
        self.stations = self._cells_with(STATION)
        self.shelves = self._cells_with(SHELF)
        floor = self._cells_with(FLOOR)
        self.pickup_cells = [
            cell for cell in floor
            if any(self.char_at(n) == SHELF for n in self._adjacent(cell))
        ]
        pickups = set(self.pickup_cells)
        # Plain floor that is not a pickup point: safe places to step aside.
        self.parking_cells = [cell for cell in floor if cell not in pickups]

        self._distance_cache: dict[Cell, dict[Cell, int]] = {}
        self._validate_content()

    # ---------------------------------------------------------------- loading
    @classmethod
    def from_string(cls, text: str, name: str = "custom") -> "Warehouse":
        return cls(text.splitlines(), name=name)

    @classmethod
    def from_file(cls, path: str | Path) -> "Warehouse":
        path = Path(path)
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            raise MapError(f"map file not found: {path}") from None
        except OSError as exc:
            raise MapError(f"cannot read map file {path}: {exc}") from exc
        return cls.from_string(text, name=path.stem)

    # ---------------------------------------------------------------- queries
    def in_bounds(self, cell: Cell) -> bool:
        row, col = cell
        return 0 <= row < self.height and 0 <= col < self.width

    def char_at(self, cell: Cell) -> str:
        if not self.in_bounds(cell):
            raise ValueError(f"cell {cell} is outside the {self.width}x{self.height} map")
        return self._rows[cell[0]][cell[1]]

    def is_walkable(self, cell: Cell) -> bool:
        return self.in_bounds(cell) and self._rows[cell[0]][cell[1]] not in BLOCKED_CHARS

    def neighbors(self, cell: Cell) -> tuple[Cell, ...]:
        """Walkable 4-connected neighbours of a cell."""
        return self._neighbors.get(cell, ())

    def cells(self) -> Iterator[tuple[Cell, str]]:
        for row, line in enumerate(self._rows):
            for col, char in enumerate(line):
                yield (row, col), char

    def distances_from(self, goal: Cell) -> dict[Cell, int]:
        """BFS distance from every reachable cell to `goal` (cached).

        Robots are ignored here, so this is an exact lower bound on travel
        time. That makes it a perfect A* heuristic.
        """
        cached = self._distance_cache.get(goal)
        if cached is not None:
            return cached
        if not self.is_walkable(goal):
            raise ValueError(f"{goal} is not a walkable cell")
        dist = {goal: 0}
        queue = deque([goal])
        while queue:
            cell = queue.popleft()
            for nxt in self.neighbors(cell):
                if nxt not in dist:
                    dist[nxt] = dist[cell] + 1
                    queue.append(nxt)
        self._distance_cache[goal] = dist
        return dist

    def distance(self, a: Cell, b: Cell) -> float:
        """Shortest static distance from a to b, or math.inf if unreachable."""
        return self.distances_from(b).get(a, math.inf)

    # ---------------------------------------------------------------- helpers
    def _adjacent(self, cell: Cell) -> list[Cell]:
        row, col = cell
        candidates = [(row + dr, col + dc) for dr, dc in DIRECTIONS]
        return [c for c in candidates if self.in_bounds(c)]

    def _cells_with(self, char: str) -> list[Cell]:
        return [cell for cell, ch in self.cells() if ch == char]

    def _validate_content(self) -> None:
        for label, found in (
            ("charger (C)", self.chargers),
            ("drop station (D)", self.stations),
            ("shelf (S)", self.shelves),
        ):
            if not found:
                raise MapError(f"map needs at least one {label}")
        if not self.pickup_cells:
            raise MapError("no floor cell is next to a shelf, so there are no pickup points")
        reachable = self.distances_from(self.chargers[0])
        required = self.chargers + self.stations + self.pickup_cells
        unreachable = [cell for cell in required if cell not in reachable]
        if unreachable:
            raise MapError(
                f"{len(unreachable)} chargers/stations/pickup points are unreachable, "
                f"e.g. {unreachable[:3]}"
            )


def _validate_shape(rows: list[str]) -> list[str]:
    cleaned = [row.rstrip() for row in rows if row.strip()]
    if not cleaned:
        raise MapError("map is empty")
    width = len(cleaned[0])
    for index, row in enumerate(cleaned):
        if len(row) != width:
            raise MapError(
                f"row {index} has length {len(row)}, expected {width} "
                "(map must be rectangular)"
            )
        bad = set(row) - VALID_CHARS
        if bad:
            raise MapError(f"row {index} contains invalid characters: {''.join(sorted(bad))!r}")
    return cleaned
