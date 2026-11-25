import pytest

from fleetflow.__main__ import main


def test_headless_and_history(tmp_path, capsys):
    db = tmp_path / "runs.db"
    assert main(["headless", "--ticks", "60", "--robots", "3", "--db", str(db)]) == 0
    assert db.exists()
    assert "throughput_per_100" in capsys.readouterr().out
    assert main(["history", "--db", str(db)]) == 0
    assert "nearest" in capsys.readouterr().out


def test_too_many_robots_reports_error(capsys):
    assert main(["headless", "--robots", "20", "--ticks", "5", "--no-save"]) == 2
    assert "error" in capsys.readouterr().err


def test_missing_map_reports_error(tmp_path, capsys):
    assert main(["headless", "--map", str(tmp_path / "missing.txt"), "--no-save"]) == 2
    assert "not found" in capsys.readouterr().err


def test_argument_validation():
    with pytest.raises(SystemExit):
        main(["headless", "--ticks", "0"])
    with pytest.raises(SystemExit):
        main(["headless", "--strategy", "magic"])


def test_benchmark_command(tmp_path):
    csv_path = tmp_path / "bench.csv"
    code = main(["benchmark", "--strategies", "fifo", "--robots", "2", "--seeds", "1",
                 "--ticks", "50", "--no-save", "--csv", str(csv_path)])
    assert code == 0 and csv_path.exists()
