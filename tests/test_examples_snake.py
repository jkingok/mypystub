"""The Snake Game example: its rules, and a game played on Toga's dummy backend."""

import importlib.util
import random
import warnings
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("toga_dummy")

from tests import support_ui  # noqa: F401 (selects the dummy backend)

EXAMPLE = (
    Path(__file__).parent.parent
    / "src/mypystub/resources/examples/claude/Snake Game.py"
)


@pytest.fixture
def snake() -> ModuleType:
    """The example, loaded as a module (its name has a space in it)."""
    spec = importlib.util.spec_from_file_location("snake_game", EXAMPLE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# -- rules --


def test_the_grid_fits_the_canvas_inside_a_wall(snake: ModuleType) -> None:
    assert snake.grid_for(320, 480) == (18, 28)  # 20 x 30 cells, less the wall
    assert snake.grid_for(10, 10) == (snake.MIN_CELLS, snake.MIN_CELLS)


def test_moving_eating_and_dying(snake: ModuleType) -> None:
    start = snake.start_snake(10, 10)
    assert start == [(5, 5), (4, 5), (3, 5)]
    step = snake.advance(start, (1, 0), None, 10, 10)
    assert step.snake == [(6, 5), (5, 5), (4, 5)] and not step.dead
    ate = snake.advance(start, (1, 0), (6, 5), 10, 10)
    assert ate.ate and len(ate.snake) == 4
    assert snake.advance([(9, 5)], (1, 0), None, 10, 10).dead  # the wall
    loop = [(1, 1), (2, 1), (2, 2), (1, 2), (0, 2)]
    assert snake.advance(loop, (0, 1), None, 10, 10).dead  # itself


def test_the_tail_cell_is_free_unless_the_snake_grows(snake: ModuleType) -> None:
    ring = [(1, 1), (2, 1), (2, 2), (1, 2)]
    assert not snake.advance(ring, (0, 1), None, 10, 10).dead
    assert snake.advance(ring, (0, 1), (1, 2), 10, 10).dead


def test_food_goes_in_an_empty_cell_or_nowhere(snake: ModuleType) -> None:
    full = [(x, y) for x in range(2) for y in range(2)]
    assert snake.place_food(full, 2, 2) is None
    food = snake.place_food(full[:3], 2, 2, rng=random.Random(1))
    assert food == (1, 1)


def test_it_speeds_up_to_a_limit(snake: ModuleType) -> None:
    assert snake.interval_for(0) == snake.START_INTERVAL
    assert snake.interval_for(1000) == snake.MIN_INTERVAL
    assert snake.clock_text(75) == "1:15"


# -- on Toga's dummy backend --


def game(snake: ModuleType, app: Any) -> Any:
    """A game in the app's window, sized like a phone's canvas, not yet running."""
    left: list[bool] = []
    window = app.main_window
    made = snake.SnakeGame(app, window, lambda: left.append(True))
    window.content = made.build()
    made.left = left
    made.on_resize(made.canvas, 320, 480)
    return made


def test_a_game_plays_draws_and_ends_without_deprecated_canvas_calls(
    snake: ModuleType, app: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        snake.SnakeGame, "begin", lambda self: setattr(self, "state", "playing")
    )
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        made = game(snake, app)
        assert (made.cols, made.rows) == (18, 28) and made.state == "ready"
        made.press("up")  # an arrow starts the game and turns
        assert made.state == "playing"
        made.last_tick = 0.0
        made.tick()
        assert made.snake[0] == (9, 13)  # moved up from (9, 14)
        assert made.canvas.root_state.drawing_actions  # a frame was drawn
        for _ in range(40):  # straight up into the wall
            if made.state == "over":
                break
            made.tick()
        assert made.state == "over"
        assert made.status_label.text == "Game over"


def test_pausing_and_back(snake: ModuleType, app: Any) -> None:
    made = game(snake, app)
    made.state = "playing"
    made.pause()
    assert made.state == "paused" and made.status_label.text == "Paused"
    made.leave()
    assert made.closed and made.left == [True]


def test_standalone_startup_gives_toga_the_game(snake: ModuleType, app: Any) -> None:
    exits: list[bool] = []
    fake = SimpleNamespace(
        main_window=app.main_window,
        loop=app.loop,
        request_exit=lambda: exits.append(True),
    )
    content = snake.standalone_startup(fake)
    assert content is not None and content.children
