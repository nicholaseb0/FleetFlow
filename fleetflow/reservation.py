"""Space-time reservation table for collision-free multi-robot planning.

Time is discrete and every robot occupies exactly one cell per tick.
Three kinds of claims are stored:

* vertex claim   (cell, t)        robot will be in `cell` at tick t
* edge claim     (a, b, t)        robot moves a -> b between t and t+1
* parking claim  cell -> (id, t0) robot stays in `cell` from t0 until it
                                  releases its reservations and replans
"""

from __future__ import annotations

from .grid import Cell


class ReservationConflict(RuntimeError):
    """Raised when a reservation would overlap another robot's claim."""


class ReservationTable:
    def __init__(self) -> None:
        self._vertex: dict[tuple[Cell, int], int] = {}
        self._edge: dict[tuple[Cell, Cell, int], int] = {}
        self._parked: dict[Cell, tuple[int, int]] = {}
        # cell -> {robot_id: last tick that robot is reserved there}
        self._latest: dict[Cell, dict[int, int]] = {}

    # ------------------------------------------------------------- queries
    def is_free(self, cell: Cell, t: int, robot_id: int) -> bool:
        """True if no *other* robot will be in `cell` at tick t."""
        owner = self._vertex.get((cell, t))
        if owner is not None and owner != robot_id:
            return False
        parked = self._parked.get(cell)
        return parked is None or parked[0] == robot_id or parked[1] > t

    def edge_free(self, a: Cell, b: Cell, t: int, robot_id: int) -> bool:
        """False if another robot moves b -> a in the same tick (head-on swap)."""
        owner = self._edge.get((b, a, t))
        return owner is None or owner == robot_id

    def can_park(self, cell: Cell, t: int, robot_id: int) -> bool:
        """True if a robot may arrive at `cell` at tick t and stay there.

        Stopping is only safe if nobody else is parked there and no other
        robot has a path through the cell at tick t or later.
        """
        parked = self._parked.get(cell)
        if parked is not None and parked[0] != robot_id:
            return False
        for other, last in self._latest.get(cell, {}).items():
            if other != robot_id and last >= t:
                return False
        return True

    def parked_by(self, cell: Cell) -> int | None:
        parked = self._parked.get(cell)
        return parked[0] if parked else None

    # ----------------------------------------------------------- mutations
    def reserve_path(self, robot_id: int, path: list[Cell], start_t: int) -> None:
        """Claim path[k] at tick start_t + k, then park on the last cell.

        The whole path is validated before anything is written, so a failed
        reservation leaves the table unchanged.
        """
        if not path:
            raise ValueError("path must contain at least the start cell")
        for k, cell in enumerate(path):
            t = start_t + k
            if not self.is_free(cell, t, robot_id):
                raise ReservationConflict(f"robot {robot_id}: {cell} is taken at t={t}")
            if k and path[k - 1] != cell and not self.edge_free(path[k - 1], cell, t - 1, robot_id):
                raise ReservationConflict(f"robot {robot_id}: swap conflict into {cell} at t={t}")
        end_t = start_t + len(path) - 1
        if not self.can_park(path[-1], end_t, robot_id):
            raise ReservationConflict(f"robot {robot_id}: cannot park at {path[-1]}")

        for k, cell in enumerate(path):
            t = start_t + k
            self._vertex[(cell, t)] = robot_id
            latest = self._latest.setdefault(cell, {})
            latest[robot_id] = max(t, latest.get(robot_id, t))
            if k and path[k - 1] != cell:
                self._edge[(path[k - 1], cell, t - 1)] = robot_id
        self.park(robot_id, path[-1], end_t)

    def park(self, robot_id: int, cell: Cell, since: int) -> None:
        current = self._parked.get(cell)
        if current is not None and current[0] != robot_id:
            raise ReservationConflict(f"{cell} is already parked by robot {current[0]}")
        stale = [c for c, (rid, _) in self._parked.items() if rid == robot_id and c != cell]
        for other_cell in stale:
            del self._parked[other_cell]
        self._parked[cell] = (robot_id, since)

    def release(self, robot_id: int) -> None:
        """Drop every claim held by a robot (done right before it replans)."""
        self._vertex = {k: v for k, v in self._vertex.items() if v != robot_id}
        self._edge = {k: v for k, v in self._edge.items() if v != robot_id}
        self._parked = {c: p for c, p in self._parked.items() if p[0] != robot_id}
        for latest in self._latest.values():
            latest.pop(robot_id, None)

    def prune(self, before_t: int) -> None:
        """Forget claims in the past; they can never conflict again."""
        self._vertex = {k: v for k, v in self._vertex.items() if k[1] >= before_t}
        self._edge = {k: v for k, v in self._edge.items() if k[2] >= before_t}
