"""Reproducible benchmarks: every number comes from an actual simulation run.

Runs are deterministic for a given (map, config, seed), apart from
`avg_plan_ms`, which is wall-clock time measured on your machine.
"""

from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean, pstdev
from typing import Callable, Sequence

from .config import ConfigError, SimConfig
from .grid import Warehouse
from .simulation import Simulation
from .storage import RunStore


def run_single(warehouse: Warehouse, config: SimConfig, ticks: int) -> dict:
    summary = Simulation(warehouse, config).run(ticks)
    return {"strategy": config.strategy, "robots": config.num_robots, "seed": config.seed, **summary}


def run_benchmark(
    warehouse: Warehouse,
    strategies: Sequence[str],
    robot_counts: Sequence[int],
    seeds: Sequence[int],
    ticks: int,
    arrival_rate: float,
    store: RunStore | None = None,
    progress: Callable[[dict], None] | None = None,
) -> list[dict]:
    if not strategies or not robot_counts or not seeds:
        raise ValueError("strategies, robot counts and seeds must not be empty")
    if ticks < 1:
        raise ValueError("ticks must be >= 1")
    if max(robot_counts) > len(warehouse.chargers):
        raise ConfigError(f"map '{warehouse.name}' has only {len(warehouse.chargers)} chargers")

    rows = []
    for strategy in strategies:
        for robots in robot_counts:
            for seed in seeds:
                config = SimConfig(num_robots=robots, strategy=strategy, seed=seed, arrival_rate=arrival_rate)
                row = run_single(warehouse, config, ticks)
                if store is not None:
                    store.save_run(warehouse.name, config, row)
                rows.append(row)
                if progress is not None:
                    progress(row)
    return rows


def aggregate(rows: list[dict]) -> list[dict]:
    """Average each (strategy, robots) group over its seeds."""
    groups: dict[tuple[str, int], list[dict]] = {}
    for row in rows:
        groups.setdefault((row["strategy"], row["robots"]), []).append(row)
    result = []
    for (strategy, robots), group in sorted(groups.items()):
        throughput = [r["throughput_per_100"] for r in group]
        result.append({
            "strategy": strategy,
            "robots": robots,
            "runs": len(group),
            "throughput_mean": mean(throughput),
            "throughput_std": pstdev(throughput) if len(group) > 1 else 0.0,
            "completed_mean": mean(r["tasks_completed"] for r in group),
            "avg_completion_time": mean(r["avg_completion_time"] for r in group),
            "avg_assignment_wait": mean(r["avg_assignment_wait"] for r in group),
            "deadlock_recoveries": mean(r["deadlock_recoveries"] for r in group),
            "collisions": sum(r["collisions"] for r in group),
            "avg_plan_ms": mean(r["avg_plan_ms"] for r in group),
        })
    return result


def format_table(summary_rows: list[dict]) -> str:
    header = (f"{'strategy':<9}{'robots':>7}{'runs':>6}{'thr/100 ticks':>18}{'completed':>11}"
              f"{'cycle time':>12}{'assign wait':>13}{'recoveries':>12}{'collisions':>12}{'plan ms':>9}")
    lines = [header, "-" * len(header)]
    for r in summary_rows:
        throughput = f"{r['throughput_mean']:.2f} +/- {r['throughput_std']:.2f}"
        lines.append(
            f"{r['strategy']:<9}{r['robots']:>7}{r['runs']:>6}{throughput:>18}{r['completed_mean']:>11.1f}"
            f"{r['avg_completion_time']:>12.1f}{r['avg_assignment_wait']:>13.1f}"
            f"{r['deadlock_recoveries']:>12.1f}{r['collisions']:>12}{r['avg_plan_ms']:>9.2f}"
        )
    return "\n".join(lines)


def write_csv(rows: list[dict], path: str | Path) -> None:
    if not rows:
        raise ValueError("no rows to write")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
