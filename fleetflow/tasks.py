"""Delivery tasks and a seeded task generator."""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .grid import Cell, Warehouse


@dataclass
class Task:
    id: int
    pickup: Cell
    dropoff: Cell
    created_at: int
    assigned_at: int | None = None
    picked_at: int | None = None
    completed_at: int | None = None
    robot_id: int | None = None


class TaskGenerator:
    """Creates tasks as a Poisson process with `arrival_rate` tasks per tick.

    It owns its own random.Random, so with the same seed every scheduling
    strategy receives the identical stream of tasks. That makes strategy
    comparisons fair.
    """

    def __init__(self, warehouse: Warehouse, arrival_rate: float, rng: random.Random) -> None:
        if not math.isfinite(arrival_rate) or arrival_rate < 0:
            raise ValueError(f"arrival_rate must be a finite number >= 0, got {arrival_rate}")
        self.warehouse = warehouse
        self.rate = arrival_rate
        self._rng = rng
        self._next_id = 0

    def generate(self, tick: int) -> list[Task]:
        tasks = []
        for _ in range(self._poisson_count()):
            tasks.append(
                Task(
                    id=self._next_id,
                    pickup=self._rng.choice(self.warehouse.pickup_cells),
                    dropoff=self._rng.choice(self.warehouse.stations),
                    created_at=tick,
                )
            )
            self._next_id += 1
        return tasks

    def _poisson_count(self) -> int:
        """Knuth's algorithm: fine for the small rates used here."""
        if self.rate == 0:
            return 0
        limit = math.exp(-self.rate)
        count = 0
        product = self._rng.random()
        while product > limit:
            count += 1
            product *= self._rng.random()
        return count
