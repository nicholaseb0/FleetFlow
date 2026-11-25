"""Validated simulation settings."""

from __future__ import annotations

import math
from dataclasses import dataclass

from .scheduler import STRATEGIES


class ConfigError(ValueError):
    """Raised for invalid simulation settings."""


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return (isinstance(value, (int, float)) and not isinstance(value, bool)
            and math.isfinite(value))


@dataclass(frozen=True)
class SimConfig:
    num_robots: int = 5
    strategy: str = "nearest"
    seed: int = 42
    arrival_rate: float = 0.08      # average new tasks per tick
    service_ticks: int = 3          # ticks spent picking or dropping
    battery_capacity: float = 100.0
    move_cost: float = 0.5          # energy per cell moved
    idle_cost: float = 0.05         # energy per tick standing still off-charger
    charge_rate: float = 2.0        # energy per tick on the charger
    battery_reserve: float = 10.0   # never dispatch below this after a trip
    stuck_threshold: int = 6        # failed plans before stepping aside
    plan_slack: int = 60            # extra ticks A* may spend beyond the static distance

    def __post_init__(self) -> None:
        errors: list[str] = []

        def check(ok: bool, message: str) -> None:
            if not ok:
                errors.append(message)

        check(_is_int(self.num_robots) and self.num_robots >= 1, "num_robots must be an integer >= 1")
        check(self.strategy in STRATEGIES, f"strategy must be one of {sorted(STRATEGIES)}")
        check(_is_int(self.seed), "seed must be an integer")
        check(_is_number(self.arrival_rate) and 0 <= self.arrival_rate <= 5,
              "arrival_rate must be between 0 and 5")
        check(_is_int(self.service_ticks) and self.service_ticks >= 0, "service_ticks must be an integer >= 0")
        check(_is_number(self.battery_capacity) and self.battery_capacity > 0, "battery_capacity must be > 0")
        check(_is_number(self.move_cost) and self.move_cost >= 0, "move_cost must be >= 0")
        check(_is_number(self.idle_cost) and self.idle_cost >= 0, "idle_cost must be >= 0")
        check(_is_number(self.charge_rate) and self.charge_rate > 0, "charge_rate must be > 0")
        check(_is_number(self.battery_reserve) and _is_number(self.battery_capacity)
              and 0 <= self.battery_reserve < self.battery_capacity,
              "battery_reserve must be >= 0 and below battery_capacity")
        check(_is_int(self.stuck_threshold) and self.stuck_threshold >= 1, "stuck_threshold must be an integer >= 1")
        check(_is_int(self.plan_slack) and self.plan_slack >= 1, "plan_slack must be an integer >= 1")

        if errors:
            raise ConfigError("; ".join(errors))
