import pytest

from fleetflow.benchmark import aggregate, format_table, run_benchmark, write_csv
from fleetflow.storage import RunStore


def test_benchmark_covers_every_combination(small_map, tmp_path):
    rows = run_benchmark(small_map, ["fifo", "greedy"], [1, 2], [1, 2], ticks=100, arrival_rate=0.1)
    assert len(rows) == 8
    summary = aggregate(rows)
    assert len(summary) == 4
    assert all(r["runs"] == 2 for r in summary)
    table = format_table(summary)
    assert "fifo" in table and "greedy" in table
    out = tmp_path / "bench.csv"
    write_csv(rows, out)
    assert len(out.read_text().strip().splitlines()) == 9


def test_benchmark_saves_every_run(small_map):
    with RunStore(":memory:") as store:
        rows = run_benchmark(small_map, ["nearest"], [2], [1, 2, 3], ticks=50, arrival_rate=0.1, store=store)
        assert len(store.recent_runs(100)) == len(rows) == 3


def test_benchmark_validates_input(small_map):
    with pytest.raises(ValueError):
        run_benchmark(small_map, [], [1], [1], ticks=10, arrival_rate=0.1)
    with pytest.raises(ValueError):
        run_benchmark(small_map, ["fifo"], [1], [1], ticks=0, arrival_rate=0.1)
    with pytest.raises(ValueError, match="chargers"):
        run_benchmark(small_map, ["fifo"], [5], [1], ticks=10, arrival_rate=0.1)
