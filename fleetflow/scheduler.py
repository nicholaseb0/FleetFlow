"""Task assignment strategies.

Each strategy is a plain function:
    (available_robots, pending_tasks, cost, eligible) -> [(robot, task), ...]

`cost(robot, task)` is the travel distance to the pickup.
`eligible(robot, task)` is the battery check.
No robot and no task appears in more than one pair.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable, Sequence

if TYPE_CHECKING:
    from .robot import Robot
    from .tasks import Task

CostFn = Callable[["Robot", "Task"], float]
EligibleFn = Callable[["Robot", "Task"], bool]
Assignment = list[tuple["Robot", "Task"]]


def _by_age(task: "Task") -> tuple[int, int]:
    return (task.created_at, task.id)


def assign_fifo(robots: Sequence["Robot"], tasks: Sequence["Task"],
                cost: CostFn, eligible: EligibleFn) -> Assignment:
    """Baseline: oldest task goes to the lowest-numbered capable robot.
    Ignores distance entirely."""
    free = sorted(robots, key=lambda r: r.id)
    result: Assignment = []
    for task in sorted(tasks, key=_by_age):
        for robot in free:
            if eligible(robot, task):
                result.append((robot, task))
                free.remove(robot)
                break
    return result


def assign_nearest(robots: Sequence["Robot"], tasks: Sequence["Task"],
                   cost: CostFn, eligible: EligibleFn) -> Assignment:
    """Oldest task first, each to the closest capable robot.
    Fair to old tasks, locally efficient."""
    free = list(robots)
    result: Assignment = []
    for task in sorted(tasks, key=_by_age):
        candidates = [r for r in free if eligible(r, task)]
        if not candidates:
            continue
        robot = min(candidates, key=lambda r: (cost(r, task), r.id))
        result.append((robot, task))
        free.remove(robot)
    return result


def assign_greedy(robots: Sequence["Robot"], tasks: Sequence["Task"],
                  cost: CostFn, eligible: EligibleFn) -> Assignment:
    """Globally cheapest robot-task pair first, repeated.
    Minimises empty travel but can starve tasks that are far from every robot."""
    pairs = sorted(
        ((cost(r, t), t.created_at, t.id, r.id, r, t)
         for r in robots for t in tasks if eligible(r, t)),
        key=lambda p: p[:4],
    )
    used_robots: set[int] = set()
    used_tasks: set[int] = set()
    result: Assignment = []
    for _, _, task_id, robot_id, robot, task in pairs:
        if robot_id in used_robots or task_id in used_tasks:
            continue
        result.append((robot, task))
        used_robots.add(robot_id)
        used_tasks.add(task_id)
    return result


STRATEGIES: dict[str, Callable[..., Assignment]] = {
    "fifo": assign_fifo,
    "nearest": assign_nearest,
    "greedy": assign_greedy,
}
