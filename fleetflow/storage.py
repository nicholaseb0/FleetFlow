"""SQLite persistence for run summaries."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .config import SimConfig


class StorageError(RuntimeError):
    """Raised when the results database cannot be used."""


SUMMARY_COLUMNS = (
    "ticks", "tasks_created", "tasks_completed", "tasks_pending",
    "throughput_per_100", "avg_completion_time", "avg_assignment_wait",
    "distance_travelled", "collisions", "deadlock_recoveries",
    "planning_failures", "avg_plan_ms", "battery_empty_ticks",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    map_name TEXT NOT NULL,
    strategy TEXT NOT NULL,
    num_robots INTEGER NOT NULL,
    seed INTEGER NOT NULL,
    arrival_rate REAL NOT NULL,
    ticks INTEGER NOT NULL,
    tasks_created INTEGER NOT NULL,
    tasks_completed INTEGER NOT NULL,
    tasks_pending INTEGER NOT NULL,
    throughput_per_100 REAL NOT NULL,
    avg_completion_time REAL NOT NULL,
    avg_assignment_wait REAL NOT NULL,
    distance_travelled INTEGER NOT NULL,
    collisions INTEGER NOT NULL,
    deadlock_recoveries INTEGER NOT NULL,
    planning_failures INTEGER NOT NULL,
    avg_plan_ms REAL NOT NULL,
    battery_empty_ticks INTEGER NOT NULL
)
"""


class RunStore:
    def __init__(self, path: str | Path = ":memory:") -> None:
        try:
            if str(path) != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(str(path))
            self._conn.row_factory = sqlite3.Row
            self._conn.execute(SCHEMA)
            self._conn.commit()
        except (sqlite3.Error, OSError) as exc:
            raise StorageError(f"cannot open results database {path}: {exc}") from exc

    def save_run(self, map_name: str, config: SimConfig, summary: dict) -> int:
        missing = [c for c in SUMMARY_COLUMNS if c not in summary]
        if missing:
            raise ValueError(f"summary is missing fields: {missing}")
        columns = ("created_at", "map_name", "strategy", "num_robots", "seed", "arrival_rate") + SUMMARY_COLUMNS
        values = (
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            map_name, config.strategy, config.num_robots, config.seed, config.arrival_rate,
        ) + tuple(summary[c] for c in SUMMARY_COLUMNS)
        placeholders = ", ".join("?" * len(columns))
        # Column names are constants above; all values go through parameters.
        sql = f"INSERT INTO runs ({', '.join(columns)}) VALUES ({placeholders})"
        try:
            with self._conn:
                cursor = self._conn.execute(sql, values)
        except sqlite3.Error as exc:
            raise StorageError(f"could not save run: {exc}") from exc
        return int(cursor.lastrowid)

    def recent_runs(self, limit: int = 20) -> list[dict]:
        if not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be an integer >= 1")
        try:
            rows = self._conn.execute("SELECT * FROM runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        except sqlite3.Error as exc:
            raise StorageError(f"could not read runs: {exc}") from exc
        return [dict(row) for row in rows]

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "RunStore":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
