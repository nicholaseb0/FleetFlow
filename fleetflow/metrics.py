"""Counters collected during a run. Every number is measured, never estimated."""

from __future__ import annotations

from dataclasses import dataclass

from .tasks import Task


@dataclass
class Metrics:
    ticks: int = 0
    tasks_created: int = 0
    tasks_assigned: int = 0
    tasks_completed: int = 0
    total_completion_time: int = 0   # sum of (completed - created)
    total_assignment_wait: int = 0   # sum of (assigned - created)
    distance_travelled: int = 0
    robot_wait_ticks: int = 0        # robot had a task but stood still (not servicing)
    charging_ticks: int = 0
    collisions: int = 0              # independent safety check, must stay 0
    planning_calls: int = 0
    planning_failures: int = 0
    planning_seconds: float = 0.0
    deadlock_recoveries: int = 0
    battery_empty_ticks: int = 0

    def record_completion(self, task: Task) -> None:
        assert task.completed_at is not None
        self.tasks_completed += 1
        self.total_completion_time += task.completed_at - task.created_at

    def summary(self, pending: int) -> dict[str, float | int]:
        def avg(total: float, count: int) -> float:
            return round(total / count, 2) if count else 0.0

        return {
            "ticks": self.ticks,
            "tasks_created": self.tasks_created,
            "tasks_completed": self.tasks_completed,
            "tasks_pending": pending,
            "throughput_per_100": round(100 * self.tasks_completed / self.ticks, 3) if self.ticks else 0.0,
            "avg_completion_time": avg(self.total_completion_time, self.tasks_completed),
            "avg_assignment_wait": avg(self.total_assignment_wait, self.tasks_assigned),
            "distance_travelled": self.distance_travelled,
            "robot_wait_ticks": self.robot_wait_ticks,
            "charging_ticks": self.charging_ticks,
            "collisions": self.collisions,
            "planning_calls": self.planning_calls,
            "planning_failures": self.planning_failures,
            "avg_plan_ms": round(1000 * self.planning_seconds / self.planning_calls, 3) if self.planning_calls else 0.0,
            "deadlock_recoveries": self.deadlock_recoveries,
            "battery_empty_ticks": self.battery_empty_ticks,
        }
