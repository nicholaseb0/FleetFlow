import pytest

from fleetflow.config import SimConfig
from fleetflow.simulation import Simulation
from fleetflow.storage import RunStore


def test_save_and_read_back(small_map):
    sim = Simulation(small_map, SimConfig(num_robots=2, arrival_rate=0.1))
    summary = sim.run(50)
    with RunStore(":memory:") as store:
        run_id = store.save_run("small", sim.config, summary)
        rows = store.recent_runs()
    assert rows[0]["id"] == run_id
    assert rows[0]["strategy"] == sim.config.strategy
    assert rows[0]["tasks_created"] == summary["tasks_created"]


def test_incomplete_summary_rejected():
    with RunStore(":memory:") as store, pytest.raises(ValueError, match="missing"):
        store.save_run("small", SimConfig(), {"ticks": 1})


def test_database_file_and_folder_are_created(tmp_path):
    path = tmp_path / "nested" / "runs.db"
    with RunStore(path):
        pass
    assert path.exists()


def test_invalid_limit_rejected():
    with RunStore(":memory:") as store, pytest.raises(ValueError):
        store.recent_runs(0)
