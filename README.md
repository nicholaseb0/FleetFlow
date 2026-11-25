# FleetFlow — Autonomous Warehouse Robot Simulator

FleetFlow simulates a warehouse where several robots pick up packages at shelves and
deliver them to drop stations without colliding. It uses real multi-agent planning
algorithms: space-time A*, a reservation table, deadlock detection and recovery,
battery-aware dispatch, and pluggable task-assignment strategies. You can watch it
live in a Pygame window or benchmark strategies headlessly with reproducible seeds.

## Features
- **Warehouse maps** written as plain text, with validation for shape, symbols and reachability.
- **Space-time A\*** pathfinding with an exact BFS-distance heuristic.
- **Collision avoidance** through a reservation table that rules out both same-cell and head-on swap conflicts.
- **Deadlock handling.** Robots only stop where nobody else will need the cell, and robots that stay stuck step aside.
- **Battery model.** Moving and waiting cost energy and chargers refill it. A robot is only dispatched if it can finish the trip and get home.
- **Dynamic task assignment** with three strategies: `fifo`, `nearest` and `greedy`.
- **Metrics:** throughput, cycle time, assignment wait, distance, planning time, recoveries, and an independent collision audit.
- **SQLite history** of runs, plus **reproducible benchmarks** with CSV export.
- **Pygame visualizer** with pause, single-step, speed control and path overlay.
- **Tests** at both unit and integration level (pytest).

## Requirements
- Windows 10/11 with WSL 2 (Ubuntu) and VS Code with the **WSL** extension.
- Python 3.10 or newer (Ubuntu 22.04 and 24.04 both qualify).
- For the window you need WSLg, which is built into Windows 11 and into recent WSL on Windows 10 (`wsl --update`).
  The headless and benchmark commands work without it.

## Installation (WSL Ubuntu)
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
cd ~/projects/fleetflow          # keep the project in the Linux filesystem, not /mnt/c (much faster)
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```
In VS Code, run `code .` from that folder in WSL. VS Code reopens in WSL mode and uses
`.venv` because of `.vscode/settings.json`. The Testing panel then discovers the pytest suite.

## Usage
```bash
python -m fleetflow run                                   # visual simulator, defaults
python -m fleetflow run --robots 8 --strategy greedy --rate 0.15
python -m fleetflow run --map fleetflow/maps/narrow.txt --robots 4
python -m fleetflow headless --ticks 2000 --robots 6       # prints and saves a summary
python -m fleetflow benchmark --robots 3 5 8 --seeds 1 2 3 --ticks 1500 --csv results/benchmark.csv
python -m fleetflow history                               # recently saved runs
python -m fleetflow --help                                # every option
```
**Visual controls:** Space pauses or resumes. N or Right steps one tick while paused.
`+`/`-` changes speed, P toggles path lines, and Esc or Q quits.

**What you see:** brown cells are shelves and beige cells are pickup points. Blue `D` cells are
drop stations and green squares are chargers. Yellow dots are waiting tasks. A coloured ring
marks a robot's current target, a yellow badge means it is carrying a package, and the bar
under each robot shows its battery.

## Project structure
```
fleetflow/grid.py         map parsing, validation, BFS distances
fleetflow/reservation.py  space-time reservation table
fleetflow/pathfinding.py  space-time A*, evasion search
fleetflow/tasks.py        Task + seeded Poisson TaskGenerator
fleetflow/robot.py        Robot state and phases
fleetflow/scheduler.py    assignment strategies
fleetflow/config.py       validated SimConfig
fleetflow/simulation.py   the tick loop (all rules live here)
fleetflow/metrics.py      counters and summary
fleetflow/storage.py      SQLite run history
fleetflow/benchmark.py    reproducible multi-seed benchmarks
fleetflow/visualizer.py   Pygame front end (presentation only)
fleetflow/__main__.py     CLI
```

## Architecture
```
            ┌─────────────┐     reads      ┌──────────────┐
 CLI ──────▶│ Simulation  │───────────────▶│  Warehouse   │ (static map + BFS cache)
 Visualizer │  tick loop  │                └──────────────┘
 Benchmark  │             │── assigns ────▶ scheduler (fifo | nearest | greedy)
            │             │── plans ──────▶ pathfinding (space-time A*)
            │             │                    │ queries/claims
            │             │── owns ───────▶ ReservationTable
            │             │── records ────▶ Metrics ──▶ storage (SQLite)
            └─────────────┘
```
`Simulation` is the only place where rules live. The visualizer just reads state, which
lets the same engine run headless in tests and benchmarks.

## How it works

### The tick loop (`simulation.py`)
Each tick runs these steps in order:
1. New tasks arrive.
2. Robots with no work are assigned tasks.
3. Robots without a path plan one.
4. Every robot moves one cell or waits.
5. Arrivals, service time, battery and charging are updated.
6. An independent audit counts any two robots on the same cell or swapping cells.

The audit is separate from the planner on purpose. If the planner had a bug, the
`collisions` metric would expose it.

### Space-time A* (`pathfinding.py`)
Ordinary A* searches over cells. Here the state is `(cell, tick)`, so "wait one tick"
is a legal move with cost 1. The heuristic is the exact BFS distance to the goal on
the empty map, which is admissible and consistent. Every route to `(cell, t)` costs
`t - start`, so the first time a state is discovered is good enough and no
re-opening is needed. The search ends when the robot reaches the goal at a tick from
which it can safely stay there. A `horizon` bounds the search so impossible requests
fail quickly.

### Reservation table and collision avoidance (`reservation.py`)
This is prioritized, or cooperative, planning (Silver, 2005). Robots plan one at a time,
and each plan becomes obstacles for later planners. The table stores three kinds of claims:
- **Vertex claims** `(cell, t)` prevent two robots in one cell.
- **Edge claims** `(a, b, t)` prevent head-on swaps.
- **Parking claims** keep a robot on its final cell from arrival until it replans.

### Deadlock handling
- *Prevention:* a robot may only finish its path on a cell that no other robot is
  scheduled to pass through later (`can_park`). This rules out the common case of
  a robot stopping in front of another robot's planned route.
- *Detection and recovery:* when planning fails, the robot stays put and retries next tick.
  After `stuck_threshold` consecutive failures, it uses BFS to find the nearest plain-floor
  cell that is safe to stop on, steps aside, and then retries its real goal. Robots that
  have been stuck longest plan first. Each step-aside is counted in `deadlock_recoveries`.

This approach is practical rather than provably complete. Prioritized planning can miss
solutions that a joint search like CBS would find.

### Battery management
Moving costs `move_cost` per cell, standing still away from the charger costs `idle_cost`
per tick, and a robot with no task on its own charger gains `charge_rate` per tick. A task
is only assigned if the robot has enough energy for three legs (to the pickup, to the
station, and back to its charger) with a 25% slack, plus service time, while still keeping
`battery_reserve`. Robots with no work go home and charge. Any tick where a battery would
have gone below zero is counted in `battery_empty_ticks`, so a weakness in the energy model
shows up instead of being hidden.

### Task assignment strategies (`scheduler.py`)
| Strategy | Rule | Trade-off |
|---|---|---|
| `fifo` | oldest task goes to the lowest-id capable robot | baseline that ignores distance |
| `nearest` | oldest task first, each to the closest capable robot | fair to old tasks and locally efficient |
| `greedy` | cheapest robot-task pair overall first, repeated | least empty travel, but can starve distant tasks |

### Metrics
- `throughput_per_100`: completed tasks per 100 ticks.
- `avg_completion_time`: ticks from a task's creation to its delivery (cycle time).
- `avg_assignment_wait`: ticks a task waits before a robot is assigned.
- `avg_plan_ms`: measured wall-clock time per planning call. It is the only metric that varies between identical runs.

## Benchmarks
The benchmark runs every combination of strategy, robot count and seed on the same map.
The task generator has its own seeded RNG, so with the same seed all strategies receive
an identical task stream (common random numbers). Results are averaged over seeds and
reported with their standard deviation.

```bash
python -m fleetflow benchmark --robots 3 5 8 --seeds 1 2 3 4 5 --ticks 2000 --rate 0.12 --csv results/benchmark.csv
```

**Results:** _run the command above and paste the table here, together with your CPU
and Python version. No numbers are included in this repository that were not produced
by running it._

## Testing
```bash
pytest            # all tests
pytest -v tests/test_pathfinding.py
```
- Unit tests cover map validation, the reservation table, A* optimality and conflict-freedom, the task generator, strategies and config validation.
- Integration tests check that full runs have zero collisions, that runs are deterministic, that all tasks finish once arrivals stop, that low-battery robots charge before dispatch, and the CLI, SQLite and benchmark pipeline.
- The visualizer test renders frames with SDL's dummy driver, so it needs no screen.

## Map format
Maps are rectangular text files, one character per cell. `#` is a wall, `S` a shelf
(blocked), `.` floor, `C` a charger (one per robot) and `D` a drop station. Floor cells
next to a shelf become pickup points. The loader rejects maps that are not rectangular,
contain unknown characters, lack a charger, station or shelf, or have unreachable
points of interest.

## Limitations and next steps
- Prioritized planning is incomplete. Conflict-Based Search (CBS) would be the natural upgrade.
- Robots heading home are not available for new tasks until they arrive.
- The `greedy` strategy can starve distant tasks. An age penalty or the Hungarian algorithm would address this.
- Battery use is a linear model and does not account for payload.
