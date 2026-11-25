"""Pygame front end. Pure presentation: every rule lives in Simulation."""

from __future__ import annotations

import pygame

from .grid import CHARGER, SHELF, STATION, WALL, Cell
from .simulation import Simulation

BACKGROUND = (24, 26, 31)
PANEL = (17, 24, 39)
FLOOR_COLOR = (229, 231, 235)
PICKUP_COLOR = (243, 237, 222)
GRID_LINE = (209, 213, 219)
WALL_COLOR = (55, 65, 81)
SHELF_COLOR = (180, 132, 82)
SHELF_EDGE = (140, 100, 60)
STATION_COLOR = (59, 130, 246)
CHARGER_COLOR = (34, 197, 94)
TASK_COLOR = (234, 179, 8)
TEXT = (229, 231, 235)
MUTED = (156, 163, 175)
WHITE = (255, 255, 255)
ROBOT_COLORS = [(239, 68, 68), (168, 85, 247), (14, 165, 233), (249, 115, 22),
                (20, 184, 166), (236, 72, 153), (132, 204, 22), (99, 102, 241)]

PANEL_WIDTH = 320
MIN_HEIGHT = 600
MAX_SPEED = 60


class VisualizerError(RuntimeError):
    """Raised when a window cannot be opened."""


class Visualizer:
    def __init__(self, sim: Simulation, cell_size: int = 40, ticks_per_second: int = 8, fps: int = 60) -> None:
        self.sim = sim
        self.cell = cell_size
        self.fps = fps
        self.ticks_per_second = max(1, min(MAX_SPEED, ticks_per_second))
        self.paused = False
        self.show_paths = True
        self.grid_width = sim.warehouse.width * cell_size
        grid_height = sim.warehouse.height * cell_size
        try:
            pygame.display.init()   # no pygame.init(): avoids audio errors on WSL
            pygame.font.init()
            self.screen = pygame.display.set_mode((self.grid_width + PANEL_WIDTH, max(grid_height, MIN_HEIGHT)))
        except pygame.error as exc:
            raise VisualizerError(
                f"could not open a window ({exc}). On WSL this needs WSLg "
                "(Windows 11, or Windows 10 with an up-to-date WSL). "
                "You can still use the 'headless' and 'benchmark' commands."
            ) from exc
        pygame.display.set_caption("FleetFlow - warehouse robot simulator")
        self.title_font = pygame.font.Font(None, 32)
        self.font = pygame.font.Font(None, 22)
        self.small = pygame.font.Font(None, 18)
        self._pickups = set(sim.warehouse.pickup_cells)

    # ------------------------------------------------------------ main loop
    def run(self, max_ticks: int | None = None) -> None:
        clock = pygame.time.Clock()
        backlog = 0.0
        running = True
        while running:
            dt = clock.tick(self.fps) / 1000.0
            running = self._handle_events(max_ticks)
            finished = max_ticks is not None and self.sim.tick >= max_ticks
            if not self.paused and not finished:
                backlog = min(backlog + dt * self.ticks_per_second, 5.0)
                while backlog >= 1.0:
                    self.sim.step()
                    backlog -= 1.0
                    if max_ticks is not None and self.sim.tick >= max_ticks:
                        break
            self.render()
        pygame.quit()

    def _handle_events(self, max_ticks: int | None) -> bool:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False
            if event.type != pygame.KEYDOWN:
                continue
            key = event.key
            if key in (pygame.K_ESCAPE, pygame.K_q):
                return False
            if key == pygame.K_SPACE:
                self.paused = not self.paused
            elif key in (pygame.K_RIGHT, pygame.K_n) and self.paused:
                if max_ticks is None or self.sim.tick < max_ticks:
                    self.sim.step()
            elif key in (pygame.K_UP, pygame.K_EQUALS, pygame.K_PLUS, pygame.K_KP_PLUS):
                self.ticks_per_second = min(MAX_SPEED, self.ticks_per_second * 2)
            elif key in (pygame.K_DOWN, pygame.K_MINUS, pygame.K_KP_MINUS):
                self.ticks_per_second = max(1, self.ticks_per_second // 2)
            elif key == pygame.K_p:
                self.show_paths = not self.show_paths
        return True

    # ------------------------------------------------------------ drawing
    def render(self) -> None:
        self.screen.fill(BACKGROUND)
        self._draw_grid()
        self._draw_tasks()
        if self.show_paths:
            self._draw_paths()
        self._draw_robots()
        self._draw_panel()
        pygame.display.flip()

    def _center(self, cell: Cell) -> tuple[int, int]:
        row, col = cell
        return col * self.cell + self.cell // 2, row * self.cell + self.cell // 2

    def _draw_grid(self) -> None:
        c = self.cell
        for (row, col), char in self.sim.warehouse.cells():
            rect = pygame.Rect(col * c, row * c, c, c)
            if char == WALL:
                pygame.draw.rect(self.screen, WALL_COLOR, rect)
                continue
            if char == SHELF:
                pygame.draw.rect(self.screen, SHELF_COLOR, rect)
                pygame.draw.rect(self.screen, SHELF_EDGE, rect.inflate(-6, -6), 2)
                continue
            color = STATION_COLOR if char == STATION else PICKUP_COLOR if (row, col) in self._pickups else FLOOR_COLOR
            pygame.draw.rect(self.screen, color, rect)
            pygame.draw.rect(self.screen, GRID_LINE, rect, 1)
            if char == CHARGER:
                pygame.draw.rect(self.screen, CHARGER_COLOR, rect.inflate(-c // 2, -c // 2), border_radius=3)
            elif char == STATION:
                label = self.font.render("D", True, WHITE)
                self.screen.blit(label, label.get_rect(center=rect.center))

    def _draw_tasks(self) -> None:
        radius = max(3, self.cell // 7)
        for task in self.sim.pending:
            pygame.draw.circle(self.screen, TASK_COLOR, self._center(task.pickup), radius)
        for robot in self.sim.robots:
            if robot.task is None:
                continue
            target = robot.task.dropoff if robot.carrying else robot.task.pickup
            color = ROBOT_COLORS[robot.id % len(ROBOT_COLORS)]
            pygame.draw.circle(self.screen, color, self._center(target), self.cell // 2 - 3, 2)

    def _draw_paths(self) -> None:
        for robot in self.sim.robots:
            if not robot.path:
                continue
            points = [self._center(robot.position)]
            for cell in robot.path:
                point = self._center(cell)
                if point != points[-1]:
                    points.append(point)
            if len(points) >= 2:
                pygame.draw.lines(self.screen, ROBOT_COLORS[robot.id % len(ROBOT_COLORS)], False, points, 2)

    def _draw_robots(self) -> None:
        c = self.cell
        for robot in self.sim.robots:
            color = ROBOT_COLORS[robot.id % len(ROBOT_COLORS)]
            cx, cy = self._center(robot.position)
            radius = int(c * 0.34)
            pygame.draw.circle(self.screen, color, (cx, cy), radius)
            pygame.draw.circle(self.screen, WHITE, (cx, cy), radius, 2)
            label = self.small.render(str(robot.id), True, WHITE)
            self.screen.blit(label, label.get_rect(center=(cx, cy)))
            if robot.carrying:  # package badge in the top-right corner
                box = pygame.Rect(0, 0, c // 4, c // 4)
                box.center = (cx + radius - 2, cy - radius + 2)
                pygame.draw.rect(self.screen, TASK_COLOR, box)
                pygame.draw.rect(self.screen, SHELF_EDGE, box, 1)
            # battery bar along the bottom of the cell
            fraction = max(0.0, min(1.0, robot.battery_fraction))
            bar = pygame.Rect(cx - c // 2 + 4, cy + c // 2 - 6, c - 8, 4)
            pygame.draw.rect(self.screen, WALL_COLOR, bar)
            fill = bar.copy()
            fill.width = int(bar.width * fraction)
            bar_color = CHARGER_COLOR if fraction > 0.5 else TASK_COLOR if fraction > 0.25 else ROBOT_COLORS[0]
            pygame.draw.rect(self.screen, bar_color, fill)

    def _draw_panel(self) -> None:
        sim = self.sim
        summary = sim.summary()
        x0 = self.grid_width
        pygame.draw.rect(self.screen, PANEL, pygame.Rect(x0, 0, PANEL_WIDTH, self.screen.get_height()))
        x, right, y = x0 + 16, x0 + PANEL_WIDTH - 16, 16

        self.screen.blit(self.title_font.render("FleetFlow", True, TEXT), (x, y))
        y += 30
        status = "PAUSED" if self.paused else f"running at {self.ticks_per_second} ticks/s"
        self.screen.blit(self.small.render(status, True, TASK_COLOR if self.paused else MUTED), (x, y))
        y += 26

        stats = [
            ("Tick", sim.tick),
            ("Map", sim.warehouse.name),
            ("Strategy", sim.config.strategy),
            ("Robots", sim.config.num_robots),
            ("Pending tasks", summary["tasks_pending"]),
            ("Completed", summary["tasks_completed"]),
            ("Throughput /100 ticks", f"{summary['throughput_per_100']:.2f}"),
            ("Avg cycle time", f"{summary['avg_completion_time']:.1f} ticks"),
            ("Collisions", summary["collisions"]),
            ("Deadlock recoveries", summary["deadlock_recoveries"]),
        ]
        for label, value in stats:
            self.screen.blit(self.font.render(label, True, MUTED), (x, y))
            text = self.font.render(str(value), True, TEXT)
            self.screen.blit(text, (right - text.get_width(), y))
            y += 22

        y += 12
        self.screen.blit(self.font.render("Robots", True, TEXT), (x, y))
        y += 24
        for robot in sim.robots:
            pygame.draw.circle(self.screen, ROBOT_COLORS[robot.id % len(ROBOT_COLORS)], (x + 6, y + 7), 6)
            self.screen.blit(self.small.render(f"R{robot.id}  {robot.phase.value}", True, TEXT), (x + 18, y))
            info = self.small.render(f"{robot.battery_fraction * 100:3.0f}%  done {robot.tasks_completed}", True, MUTED)
            self.screen.blit(info, (right - info.get_width(), y))
            y += 20

        controls = ["Space: pause / resume", "N or Right: step (paused)",
                    "+ / -: speed", "P: toggle paths", "Esc or Q: quit"]
        y = self.screen.get_height() - 18 * len(controls) - 12
        for line in controls:
            self.screen.blit(self.small.render(line, True, MUTED), (x, y))
            y += 18
