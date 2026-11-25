"""Robot state. Behaviour lives in Simulation so the rules are in one place."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum

from .grid import Cell
from .tasks import Task


class Phase(str, Enum):
    IDLE = "idle"              # no task
    TO_PICKUP = "to_pickup"
    PICKING = "picking"        # dwelling at the shelf
    TO_DROPOFF = "to_dropoff"
    DROPPING = "dropping"      # dwelling at the station
    TO_CHARGER = "to_charger"


@dataclass
class Robot:
    id: int
    position: Cell
    charger: Cell
    capacity: float
    battery: float
    phase: Phase = Phase.IDLE
    task: Task | None = None
    path: deque = field(default_factory=deque)  # future cells, one per tick
    dwell: int = 0                               # service ticks remaining
    detour: bool = False                         # currently stepping aside
    stuck_ticks: int = 0                         # consecutive failed plans
    moved_last_tick: bool = False
    distance_travelled: int = 0
    tasks_completed: int = 0

    @property
    def carrying(self) -> bool:
        return self.phase in (Phase.TO_DROPOFF, Phase.DROPPING)

    @property
    def battery_fraction(self) -> float:
        return self.battery / self.capacity

    def leg_target(self) -> Cell | None:
        """Where the current phase wants the robot to go."""
        if self.phase == Phase.TO_PICKUP and self.task is not None:
            return self.task.pickup
        if self.phase == Phase.TO_DROPOFF and self.task is not None:
            return self.task.dropoff
        if self.phase == Phase.TO_CHARGER:
            return self.charger
        return None
