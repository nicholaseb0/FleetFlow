"""Command-line entry point: python -m fleetflow <command> [options]"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from .benchmark import aggregate, format_table, run_benchmark, write_csv
from .config import SimConfig
from .grid import DEFAULT_MAP, Warehouse
from .scheduler import STRATEGIES
from .simulation import Simulation
from .storage import RunStore, StorageError

DEFAULT_DB = Path("results") / "fleetflow.db"


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected an integer, got {text!r}") from None
    if value < 1:
        raise argparse.ArgumentTypeError(f"must be >= 1, got {value}")
    return value


def _non_negative_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"expected a number, got {text!r}") from None
    if not math.isfinite(value) or value < 0:
        raise argparse.ArgumentTypeError(f"must be a finite number >= 0, got {text}")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fleetflow", description="Multi-robot warehouse simulator")
    sub = parser.add_subparsers(dest="command", required=True)

    def add_sim_options(p: argparse.ArgumentParser) -> None:
        p.add_argument("--map", type=Path, default=DEFAULT_MAP, help="path to a map .txt file")
        p.add_argument("--robots", type=_positive_int, default=5)
        p.add_argument("--strategy", choices=sorted(STRATEGIES), default="nearest")
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--rate", type=_non_negative_float, default=0.08, help="average new tasks per tick")
        p.add_argument("--service-ticks", type=int, default=3, help="ticks spent picking/dropping")

    run = sub.add_parser("run", help="open the visual simulator")
    add_sim_options(run)
    run.add_argument("--cell-size", type=_positive_int, default=40)
    run.add_argument("--speed", type=_positive_int, default=8, help="initial ticks per second")
    run.add_argument("--max-ticks", type=_positive_int, default=None)
    run.add_argument("--save", action="store_true", help="save the summary to the database on exit")
    run.add_argument("--db", type=Path, default=DEFAULT_DB)

    headless = sub.add_parser("headless", help="run without graphics and print a summary")
    add_sim_options(headless)
    headless.add_argument("--ticks", type=_positive_int, default=1000)
    headless.add_argument("--db", type=Path, default=DEFAULT_DB)
    headless.add_argument("--no-save", action="store_true")

    bench = sub.add_parser("benchmark", help="compare strategies over several seeds")
    bench.add_argument("--map", type=Path, default=DEFAULT_MAP)
    bench.add_argument("--strategies", nargs="+", choices=sorted(STRATEGIES), default=sorted(STRATEGIES))
    bench.add_argument("--robots", nargs="+", type=_positive_int, default=[3, 5, 8])
    bench.add_argument("--seeds", nargs="+", type=int, default=[1, 2, 3])
    bench.add_argument("--ticks", type=_positive_int, default=1500)
    bench.add_argument("--rate", type=_non_negative_float, default=0.12)
    bench.add_argument("--csv", type=Path, default=None, help="also write per-run rows to CSV")
    bench.add_argument("--db", type=Path, default=DEFAULT_DB)
    bench.add_argument("--no-save", action="store_true")

    history = sub.add_parser("history", help="show recently saved runs")
    history.add_argument("--db", type=Path, default=DEFAULT_DB)
    history.add_argument("--limit", type=_positive_int, default=15)
    return parser


def _make_config(args: argparse.Namespace) -> SimConfig:
    return SimConfig(num_robots=args.robots, strategy=args.strategy, seed=args.seed,
                     arrival_rate=args.rate, service_ticks=args.service_ticks)


def _print_summary(summary: dict) -> None:
    width = max(len(key) for key in summary)
    for key, value in summary.items():
        print(f"  {key:<{width}}  {value}")


def _cmd_run(args: argparse.Namespace) -> int:
    warehouse = Warehouse.from_file(args.map)
    sim = Simulation(warehouse, _make_config(args))
    try:
        from .visualizer import Visualizer, VisualizerError
    except ImportError:
        print("error: pygame is not installed. Run: pip install -r requirements.txt", file=sys.stderr)
        return 1
    try:
        Visualizer(sim, cell_size=args.cell_size, ticks_per_second=args.speed).run(max_ticks=args.max_ticks)
    except VisualizerError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"Visual run ended at tick {sim.tick}:")
    summary = sim.summary()
    _print_summary(summary)
    if args.save:
        with RunStore(args.db) as store:
            run_id = store.save_run(warehouse.name, sim.config, summary)
        print(f"saved as run #{run_id} in {args.db}")
    return 0


def _cmd_headless(args: argparse.Namespace) -> int:
    warehouse = Warehouse.from_file(args.map)
    config = _make_config(args)
    sim = Simulation(warehouse, config)
    summary = sim.run(args.ticks)
    print(f"map={warehouse.name} strategy={config.strategy} robots={config.num_robots} "
          f"seed={config.seed} rate={config.arrival_rate} ticks={args.ticks}")
    _print_summary(summary)
    if not args.no_save:
        with RunStore(args.db) as store:
            run_id = store.save_run(warehouse.name, config, summary)
        print(f"saved as run #{run_id} in {args.db}")
    return 0


def _cmd_benchmark(args: argparse.Namespace) -> int:
    warehouse = Warehouse.from_file(args.map)
    total = len(args.strategies) * len(args.robots) * len(args.seeds)
    done = 0

    def progress(row: dict) -> None:
        nonlocal done
        done += 1
        print(f"[{done}/{total}] {row['strategy']:<8} robots={row['robots']} seed={row['seed']} "
              f"throughput/100={row['throughput_per_100']:.2f} collisions={row['collisions']}", flush=True)

    store = None if args.no_save else RunStore(args.db)
    try:
        rows = run_benchmark(warehouse, args.strategies, args.robots, args.seeds,
                             args.ticks, args.rate, store=store, progress=progress)
    finally:
        if store is not None:
            store.close()
    print()
    print(f"map={warehouse.name} ticks={args.ticks} rate={args.rate} seeds={args.seeds}")
    print(format_table(aggregate(rows)))
    if args.csv:
        write_csv(rows, args.csv)
        print(f"\nper-run rows written to {args.csv}")
    return 0


def _cmd_history(args: argparse.Namespace) -> int:
    if not args.db.exists():
        print(f"No results database at {args.db} yet. Run 'headless' or 'benchmark' first.")
        return 0
    with RunStore(args.db) as store:
        rows = store.recent_runs(args.limit)
    if not rows:
        print("No runs recorded yet.")
        return 0
    print(f"{'id':>4}  {'created (UTC)':<26}{'map':<10}{'strategy':<9}{'robots':>7}{'seed':>6}"
          f"{'ticks':>7}{'done':>6}{'thr/100':>9}{'collisions':>11}")
    for r in rows:
        print(f"{r['id']:>4}  {r['created_at']:<26}{r['map_name']:<10}{r['strategy']:<9}{r['num_robots']:>7}"
              f"{r['seed']:>6}{r['ticks']:>7}{r['tasks_completed']:>6}{r['throughput_per_100']:>9.2f}"
              f"{r['collisions']:>11}")
    return 0


COMMANDS = {"run": _cmd_run, "headless": _cmd_headless, "benchmark": _cmd_benchmark, "history": _cmd_history}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return COMMANDS[args.command](args)
    except (ValueError, StorageError) as exc:   # MapError and ConfigError are ValueErrors
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("interrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
