"""The discrete-time simulation loop.

Every call to step() advances the world by one tick:
  1. new tasks arrive (seeded Poisson process)
  2. robots with no work are matched to waiting tasks by the chosen strategy
  3. robots without a path plan their next leg with space-time A*
  4. every robot moves one cell (or waits) along its reserved path
  5. arrivals, service time, battery and charging are updated
"""

from __future__ import annotations

import math
import random
import time
from collections import deque

from .config import ConfigError, SimConfig
from .grid import Cell, Warehouse
from .metrics import Metrics
from .pathfinding import find_evasion_cell, plan_path
from .reservation import ReservationTable
from .robot import Phase, Robot
from .scheduler import STRATEGIES
from .tasks import Task, TaskGenerator

# Real trips include waits and detours, so the dispatch energy check budgets
# 25% more than the static shortest distance.
ENERGY_SLACK = 1.25


class Simulation:
    def __init__(self, warehouse: Warehouse, config: SimConfig | None = None) -> None:
        self.config = config if config is not None else SimConfig()
        if self.config.num_robots > len(warehouse.chargers):
            raise ConfigError(
                f"{self.config.num_robots} robots requested but map '{warehouse.name}' "
                f"has only {len(warehouse.chargers)} chargers"
            )
        self.warehouse = warehouse
        self.tick = 0
        self.metrics = Metrics()
        self.table = ReservationTable()
        self.generator = TaskGenerator(warehouse, self.config.arrival_rate, random.Random(self.config.seed))
        self.pending: list[Task] = []
        self.completed: list[Task] = []
        self._assign = STRATEGIES[self.config.strategy]

        capacity = self.config.battery_capacity
        self.robots = [
            Robot(id=i, position=cell, charger=cell, capacity=capacity, battery=capacity)
            for i, cell in enumerate(warehouse.chargers[: self.config.num_robots])
        ]
        for robot in self.robots:
            self.table.park(robot.id, robot.position, 0)

    # ------------------------------------------------------------ public API
    def run(self, ticks: int) -> dict[str, float | int]:
        if not isinstance(ticks, int) or ticks < 0:
            raise ValueError("ticks must be an integer >= 0")
        for _ in range(ticks):
            self.step()
        return self.summary()

    def summary(self) -> dict[str, float | int]:
        return self.metrics.summary(pending=len(self.pending))

    def step(self) -> None:
        now = self.tick
        new_tasks = self.generator.generate(now)
        self.pending.extend(new_tasks)
        self.metrics.tasks_created += len(new_tasks)

        self._assign_tasks(now)

        # Robots that have been stuck longest plan first (simple fairness).
        for robot in sorted(self.robots, key=lambda r: (-r.stuck_ticks, r.id)):
            self._plan_if_needed(robot, now)

        previous = [robot.position for robot in self.robots]
        for robot in self.robots:
            self._move(robot)
        self._check_conflicts(previous)

        for robot in self.robots:
            self._update(robot, now + 1)

        self.tick = now + 1
        self.metrics.ticks = self.tick
        self.table.prune(self.tick)

    # ------------------------------------------------------------ assignment
    def _assign_tasks(self, now: int) -> None:
        available = [r for r in self.robots if r.task is None and not r.path]
        if not available or not self.pending:
            return
        pairs = self._assign(available, self.pending, self._travel_cost, self._has_energy_for)
        for robot, task in pairs:
            task.assigned_at = now
            task.robot_id = robot.id
            robot.task = task
            robot.phase = Phase.TO_PICKUP
            robot.detour = False
            robot.stuck_ticks = 0
            self.metrics.tasks_assigned += 1
            self.metrics.total_assignment_wait += now - task.created_at
        assigned = {task.id for _, task in pairs}
        self.pending = [t for t in self.pending if t.id not in assigned]

    def _travel_cost(self, robot: Robot, task: Task) -> float:
        return self.warehouse.distance(robot.position, task.pickup)

    def _has_energy_for(self, robot: Robot, task: Task) -> bool:
        """Only dispatch if the robot can do the whole trip and get home."""
        d = self.warehouse.distance
        trip = d(robot.position, task.pickup) + d(task.pickup, task.dropoff) + d(task.dropoff, robot.charger)
        if math.isinf(trip):
            return False
        needed = (trip * self.config.move_cost * ENERGY_SLACK
                  + 2 * self.config.service_ticks * self.config.idle_cost)
        return robot.battery - needed >= self.config.battery_reserve

    # ------------------------------------------------------------ planning
    def _plan_if_needed(self, robot: Robot, now: int) -> None:
        if robot.path or robot.dwell > 0:
            return
        if robot.task is None:
            if robot.position == robot.charger:
                robot.phase = Phase.IDLE
                return
            robot.phase = Phase.TO_CHARGER
        target = robot.leg_target()
        if target is None:
            return
        if robot.position == target:
            self._arrive(robot, now)
            return

        goal, is_detour = target, False
        if robot.stuck_ticks >= self.config.stuck_threshold:
            escape = find_evasion_cell(self.warehouse, self.table, robot.id, robot.position, now)
            if escape is not None:
                goal, is_detour = escape, True

        self.table.release(robot.id)
        distance = self.warehouse.distance(robot.position, goal)
        path = None
        if not math.isinf(distance):
            started = time.perf_counter()
            path = plan_path(self.warehouse, self.table, robot.id, robot.position, goal,
                             start_t=now, horizon=int(distance) + self.config.plan_slack)
            self.metrics.planning_seconds += time.perf_counter() - started
        self.metrics.planning_calls += 1

        if path is None:
            self.table.park(robot.id, robot.position, now)  # stay put, retry next tick
            robot.stuck_ticks += 1
            self.metrics.planning_failures += 1
            return

        self.table.reserve_path(robot.id, path, now)
        robot.path = deque(path[1:])
        robot.detour = is_detour
        robot.stuck_ticks = 0
        if is_detour:
            self.metrics.deadlock_recoveries += 1

    # ------------------------------------------------------------ movement
    def _move(self, robot: Robot) -> None:
        if not robot.path:
            robot.moved_last_tick = False
            return
        nxt = robot.path.popleft()
        robot.moved_last_tick = nxt != robot.position
        if robot.moved_last_tick:
            robot.distance_travelled += 1
            self.metrics.distance_travelled += 1
        robot.position = nxt

    def _check_conflicts(self, previous: list[Cell]) -> None:
        """Independent safety audit. Correct planning keeps this at zero."""
        occupied: set[Cell] = set()
        for robot in self.robots:
            if robot.position in occupied:
                self.metrics.collisions += 1
            occupied.add(robot.position)
        for i, a in enumerate(self.robots):
            for j in range(i + 1, len(self.robots)):
                b = self.robots[j]
                if a.position == previous[j] and b.position == previous[i] and a.position != b.position:
                    self.metrics.collisions += 1

    # ------------------------------------------------------------ state updates
    def _update(self, robot: Robot, now: int) -> None:
        cfg = self.config
        charging = robot.task is None and robot.position == robot.charger and not robot.moved_last_tick
        if robot.moved_last_tick:
            robot.battery -= cfg.move_cost
        elif charging:
            if robot.battery < robot.capacity:
                self.metrics.charging_ticks += 1
            robot.battery = min(robot.capacity, robot.battery + cfg.charge_rate)
        else:
            robot.battery -= cfg.idle_cost
            if robot.task is not None and robot.dwell == 0:
                self.metrics.robot_wait_ticks += 1
        if robot.battery < 0:
            robot.battery = 0.0
            self.metrics.battery_empty_ticks += 1

        if robot.dwell > 0:
            robot.dwell -= 1
            if robot.dwell == 0:
                self._finish_service(robot, now)
            return
        if robot.path:
            return
        if robot.detour:          # finished stepping aside; replan next tick
            robot.detour = False
            return
        if robot.position == robot.leg_target():
            self._arrive(robot, now)

    def _arrive(self, robot: Robot, now: int) -> None:
        if robot.phase == Phase.TO_PICKUP:
            robot.phase = Phase.PICKING
            self._start_service(robot, now)
        elif robot.phase == Phase.TO_DROPOFF:
            robot.phase = Phase.DROPPING
            self._start_service(robot, now)
        elif robot.phase == Phase.TO_CHARGER:
            robot.phase = Phase.IDLE

    def _start_service(self, robot: Robot, now: int) -> None:
        if self.config.service_ticks == 0:
            self._finish_service(robot, now)
        else:
            robot.dwell = self.config.service_ticks

    def _finish_service(self, robot: Robot, now: int) -> None:
        task = robot.task
        if task is None:
            return
        if robot.phase == Phase.PICKING:
            task.picked_at = now
            robot.phase = Phase.TO_DROPOFF
        elif robot.phase == Phase.DROPPING:
            task.completed_at = now
            self.completed.append(task)
            self.metrics.record_completion(task)
            robot.tasks_completed += 1
            robot.task = None
            robot.phase = Phase.IDLE
