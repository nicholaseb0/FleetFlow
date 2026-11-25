import pytest

pygame = pytest.importorskip("pygame")

from fleetflow.config import SimConfig  # noqa: E402
from fleetflow.simulation import Simulation  # noqa: E402


def test_renders_frames_without_a_display(default_map, monkeypatch):
    monkeypatch.setenv("SDL_VIDEODRIVER", "dummy")
    from fleetflow.visualizer import Visualizer

    sim = Simulation(default_map, SimConfig(num_robots=4, arrival_rate=0.2))
    vis = Visualizer(sim, cell_size=20)
    try:
        for _ in range(30):
            sim.step()
            vis.render()
    finally:
        pygame.quit()
    assert sim.tick == 30
