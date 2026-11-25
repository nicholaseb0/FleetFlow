"""Space-time A* (the core of cooperative / prioritized pathfinding).

The search state is (cell, tick) instead of just a cell, so "wait here for
one tick" is a legal move. Cells and swaps already claimed by other robots
are treated as obstacles at the specific ticks they are claimed.
"""

from __future__ import annotations

import heapq
import itertools
from collections import deque

from .grid import Cell, Warehouse
from .reservation import ReservationTable

State = tuple[Cell, int]


def plan_path(
    warehouse: Warehouse,
    table: ReservationTable,
    robot_id: int,
    start: Cell,
    goal: Cell,
    start_t: int,
    horizon: int,
) -> list[Cell] | None:
    """Return the cells occupied at ticks start_t, start_t + 1, ...

    The path ends at `goal` at a tick from which the robot can safely stay
    there. Returns None if no such path exists within `horizon` ticks.
    """
    if not warehouse.is_walkable(start):
        raise ValueError(f"start {start} is not walkable")
    if not warehouse.is_walkable(goal):
        raise ValueError(f"goal {goal} is not walkable")
    if horizon < 0:
        raise ValueError("horizon must be >= 0")

    owner = table.parked_by(goal)
    if owner is not None and owner != robot_id:
        return None  # someone is standing on the goal indefinitely: fail fast

    heuristic = warehouse.distances_from(goal)  # exact static distance
    h_start = heuristic.get(start)
    if h_start is None or h_start > horizon:
        return None

    max_t = start_t + horizon
    tie = itertools.count()
    # (f, h, tie-breaker, cell, t): lower h breaks f ties toward the goal
    open_heap: list[tuple[int, int, int, Cell, int]] = [(h_start, h_start, next(tie), start, start_t)]
    parent: dict[State, State | None] = {(start, start_t): None}

    while open_heap:
        _, _, _, cell, t = heapq.heappop(open_heap)
        if cell == goal and table.can_park(goal, t, robot_id):
            return _reconstruct(parent, (cell, t))
        if t >= max_t:
            continue
        nt = t + 1
        for nxt in (cell, *warehouse.neighbors(cell)):  # wait + 4 moves
            state = (nxt, nt)
            if state in parent:
                continue  # every route to (cell, t) costs the same, keep the first
            h = heuristic.get(nxt)
            if h is None or nt + h > max_t:
                continue
            if not table.is_free(nxt, nt, robot_id):
                continue
            if nxt != cell and not table.edge_free(cell, nxt, t, robot_id):
                continue
            parent[state] = (cell, t)
            heapq.heappush(open_heap, (nt - start_t + h, h, next(tie), nxt, nt))
    return None


def find_evasion_cell(
    warehouse: Warehouse,
    table: ReservationTable,
    robot_id: int,
    start: Cell,
    start_t: int,
    max_steps: int = 8,
) -> Cell | None:
    """Nearest plain-floor cell where a stuck robot can step aside.

    Used for deadlock recovery: moving out of the way frees the cell that
    another blocked robot is waiting for.
    """
    candidates = set(warehouse.parking_cells)
    seen = {start}
    queue = deque([(start, 0)])
    while queue:
        cell, steps = queue.popleft()
        if cell != start and cell in candidates and table.can_park(cell, start_t + steps, robot_id):
            return cell
        if steps == max_steps:
            continue
        for nxt in warehouse.neighbors(cell):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, steps + 1))
    return None


def _reconstruct(parent: dict[State, State | None], end: State) -> list[Cell]:
    path = []
    state: State | None = end
    while state is not None:
        path.append(state[0])
        state = parent[state]
    path.reverse()
    return path
