# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "toga",
# ]
# ///

"""
Classic Snake for MyPyStub, version 2, drawn on a Toga canvas.

Tap the board to start, pause and resume. Steer with the four arrows (an arrow
also starts or resumes the game). Eat the red food to grow and score. The snake
dies on the wall or on itself, and a tap starts a new game. The wait between
moves shortens as you score.

The grid is sized from the canvas, so it fills whatever space the layout gives
it, with a painted wall all round. Layout is a 3 x 3 grid: empty spacers in
the corners, an arrow on each side, and the board in the middle. Score and
time sit above, Back below.
"""

import asyncio
import random
import time
from types import SimpleNamespace

import toga
from toga.style import Pack

TARGET_CELL = 16  # wanted cell size, in the canvas's own units
MIN_CELLS = 8  # smallest playfield side, in cells
START_INTERVAL = 0.18  # seconds between moves at the start
MIN_INTERVAL = 0.07  # fastest the game gets
SPEEDUP_PER_FOOD = 0.004
FOOD_POINTS = 10
BUTTON = 64  # size of an arrow button and of the corner spacers

COLOURS = {
    "normal": {
        "backdrop": "#101418",
        "board": "#1b2630",
        "wall": "#b0805a",
        "food": "#e5484d",
        "body": "#46b06a",
        "head": "#9be89b",
    },
    "over": {
        "backdrop": "#101418",
        "board": "#1b2630",
        "wall": "#b0805a",
        "food": "#e5484d",
        "body": "#46b06a",
        "head": "#ffb454",
    },
    "paused": {
        "backdrop": "#101418",
        "board": "#141b22",
        "wall": "#5a4533",
        "food": "#7a2e30",
        "body": "#2c6a41",
        "head": "#5e8f5e",
    },
}
PAUSE_BARS = "#ffffff"

DIRECTIONS = {"up": (0, -1), "down": (0, 1), "left": (-1, 0), "right": (1, 0)}


# ---------- game rules (plain Python, no Toga) ----------


def grid_for(width, height, target=TARGET_CELL):
    """Playfield size (cols, rows) that fits a canvas, leaving a one-cell wall all round."""
    cols = max(MIN_CELLS, int(width // target) - 2)
    rows = max(MIN_CELLS, int(height // target) - 2)
    return cols, rows


def cell_size(width, height, cols, rows):
    """Square cell size that fits the playfield plus its wall into the canvas."""
    return min(width / (cols + 2), height / (rows + 2))


def opposite(a, b):
    return a[0] == -b[0] and a[1] == -b[1]


def start_snake(cols, rows):
    """Three cells, head first, in the middle of the board, heading right."""
    x, y = cols // 2, rows // 2
    return [(x, y), (x - 1, y), (x - 2, y)]


def place_food(snake, cols, rows, rng=random):
    """A random empty cell, or None if the snake fills the whole board."""
    taken = set(snake)
    free = [(x, y) for x in range(cols) for y in range(rows) if (x, y) not in taken]
    return rng.choice(free) if free else None


def advance(snake, direction, food, cols, rows):
    """Move one cell. Returns SimpleNamespace(snake, ate, dead).

    The tail cell is free to move into, because the tail moves away on the same
    step, unless the snake just ate and so grows.
    """
    head = (snake[0][0] + direction[0], snake[0][1] + direction[1])
    ate = head == food
    body = snake if ate else snake[:-1]
    in_wall = not (0 <= head[0] < cols and 0 <= head[1] < rows)
    if in_wall or head in body:
        return SimpleNamespace(snake=snake, ate=False, dead=True)
    return SimpleNamespace(snake=[head] + body, ate=ate, dead=False)


def wall_cells(cols, rows):
    """Cells of the wall ring, in playfield coordinates (so -1 and cols/rows)."""
    return [
        (x, y)
        for x in range(-1, cols + 1)
        for y in range(-1, rows + 1)
        if x in (-1, cols) or y in (-1, rows)
    ]


def interval_for(foods):
    return max(MIN_INTERVAL, START_INTERVAL - SPEEDUP_PER_FOOD * foods)


def clock_text(seconds):
    minutes, secs = divmod(int(seconds), 60)
    return f"{minutes}:{secs:02d}"


# ---------- the app (Toga UI) ----------


class SnakeGame:
    def __init__(self, app, window, on_exit):
        self.app = app
        self.window = window
        self.on_exit = on_exit
        self.best = 0
        self.size = (0, 0)  # canvas size, set by on_resize
        self.cols = self.rows = None  # playfield size, set from the canvas
        self.task = None
        self.generation = 0  # lets a stale game loop notice it has been replaced
        self.closed = False
        self.reset()

        self.score_label = toga.Label("", style=Pack(flex=2, font_weight="bold"))
        self.status_label = toga.Label("", style=Pack(flex=1, text_align="center"))
        self.time_label = toga.Label("", style=Pack(flex=1, text_align="right"))
        self.canvas = toga.Canvas(
            style=Pack(flex=1), on_resize=self.on_resize, on_press=self.on_canvas_press
        )
        self.update_labels()

    # -- state --

    def reset(self):
        """A fresh game on the current grid. States: ready, playing, paused, over."""
        if self.cols is None:
            self.snake, self.food = [], None
        else:
            self.snake = start_snake(self.cols, self.rows)
            self.food = place_food(self.snake, self.cols, self.rows)
        self.direction = (1, 0)
        self.queue = []  # turns tapped but not yet made, at most two
        self.foods = 0
        self.score = 0
        self.elapsed = 0.0
        self.last_tick = 0.0
        self.state = "ready"

    def fit_grid(self):
        """Size the grid from the canvas and start a fresh game on it."""
        width, height = self.size
        self.cols, self.rows = grid_for(width, height)
        self.reset()

    def status(self):
        return {
            "ready": "Tap to start",
            "playing": "",
            "paused": "Paused",
            "over": "Game over",
        }[self.state]

    def update_labels(self):
        self.score_label.text = f"Score {self.score} (best {self.best})"
        self.status_label.text = self.status()
        self.time_label.text = f"⏱ {clock_text(self.elapsed)}"

    # -- layout --

    def build(self):
        def spacer():
            return toga.Box(style=Pack(width=BUTTON, height=BUTTON))

        def arrow(text, name, **style):
            return toga.Button(
                text,
                on_press=lambda w: self.press(name),
                style=Pack(font_size=26, **style),
            )

        def side_arrow(text, name):
            # A column with flexible gaps above and below keeps the button
            # centred on the board's height.
            return toga.Box(
                children=[
                    toga.Box(style=Pack(flex=1)),
                    arrow(text, name, width=BUTTON, height=BUTTON),
                    toga.Box(style=Pack(flex=1)),
                ],
                style=Pack(direction="column", width=BUTTON),
            )

        header = toga.Box(
            children=[self.score_label, self.status_label, self.time_label],
            style=Pack(direction="row", margin=8),
        )
        top_row = toga.Box(
            children=[spacer(), arrow("▲", "up", flex=1, height=BUTTON), spacer()],
            style=Pack(direction="row"),
        )
        middle_row = toga.Box(
            children=[side_arrow("◀", "left"), self.canvas, side_arrow("▶", "right")],
            style=Pack(direction="row", flex=1),
        )
        bottom_row = toga.Box(
            children=[spacer(), arrow("▼", "down", flex=1, height=BUTTON), spacer()],
            style=Pack(direction="row"),
        )
        footer = toga.Box(
            children=[
                toga.Button(
                    "⬅ Back", on_press=lambda w: self.leave(), style=Pack(flex=1)
                )
            ],
            style=Pack(direction="row", margin_top=4, margin_bottom=14),
        )
        return toga.Box(
            children=[header, top_row, middle_row, bottom_row, footer],
            style=Pack(direction="column", flex=1, margin=6),
        )

    def on_resize(self, widget, width, height, **kwargs):
        self.size = (width, height)
        if self.state == "ready":  # only re-grid before a game is under way
            self.fit_grid()
            self.update_labels()
        self.draw()

    # -- controls --

    def on_canvas_press(self, widget, x, y, **kwargs):
        """Tap the board: start, pause or resume, or start again after game over."""
        if self.cols is None:
            return
        if self.state == "playing":
            self.pause()
        else:
            self.start_or_resume()

    def start_or_resume(self):
        if self.state == "over":
            self.fit_grid()
        self.begin()

    def press(self, name):
        if self.cols is None:
            return
        if self.state != "playing":
            self.start_or_resume()
        want = DIRECTIONS[name]
        last = self.queue[-1] if self.queue else self.direction
        # No U-turns into the snake's own neck, and no repeats of the same turn.
        if want != last and not opposite(want, last) and len(self.queue) < 2:
            self.queue.append(want)

    def begin(self):
        self.state = "playing"
        self.last_tick = time.monotonic()  # time spent paused doesn't count
        self.generation += 1
        if self.task is not None:
            self.task.cancel()
        self.task = self.app.loop.create_task(self.run(self.generation))
        self.update_labels()
        self.draw()

    def pause(self):
        self.state = "paused"
        self.generation += 1
        if self.task is not None:
            self.task.cancel()
            self.task = None
        self.update_labels()
        self.draw()

    def leave(self):
        self.closed = True
        self.generation += 1
        if self.task is not None:
            self.task.cancel()
        self.on_exit()

    # -- the game loop --

    async def run(self, generation):
        while (
            self.state == "playing"
            and generation == self.generation
            and not self.closed
        ):
            await asyncio.sleep(interval_for(self.foods))
            if (
                self.state == "playing"
                and generation == self.generation
                and not self.closed
            ):
                self.tick()

    def tick(self):
        now = time.monotonic()
        self.elapsed += now - self.last_tick
        self.last_tick = now

        if self.queue:
            self.direction = self.queue.pop(0)
        result = advance(self.snake, self.direction, self.food, self.cols, self.rows)
        if result.dead:
            self.finish()
        else:
            self.snake = result.snake
            if result.ate:
                self.foods += 1
                self.score += FOOD_POINTS
                self.food = place_food(self.snake, self.cols, self.rows)
                if self.food is None:  # the snake fills the board: you win
                    self.finish()
        self.update_labels()
        self.draw()

    def finish(self):
        self.state = "over"
        self.best = max(self.best, self.score)

    # -- drawing --

    def draw(self):
        width, height = self.size
        if width <= 0 or height <= 0 or self.cols is None or self.rows is None:
            return
        colours = COLOURS[self.state if self.state in ("over", "paused") else "normal"]
        cell = cell_size(width, height, self.cols, self.rows)
        left = (width - cell * (self.cols + 2)) / 2
        top = (height - cell * (self.rows + 2)) / 2

        canvas = self.canvas

        def squares(cells, gap):
            # Cell (0, 0) is the playfield's corner, one cell in from the wall.
            for x, y in cells:
                canvas.rect(
                    left + (x + 1) * cell + gap,
                    top + (y + 1) * cell + gap,
                    cell - 2 * gap,
                    cell - 2 * gap,
                )

        gap = max(1.0, cell * 0.08)
        # Start again from nothing: each frame is drawn whole
        canvas.root_state.drawing_actions.clear()
        with canvas.fill(color=colours["backdrop"]):
            canvas.rect(0, 0, width, height)
        with canvas.fill(color=colours["board"]):
            canvas.rect(left + cell, top + cell, cell * self.cols, cell * self.rows)
        with canvas.fill(color=colours["wall"]):
            squares(wall_cells(self.cols, self.rows), gap * 0.5)
        if self.food is not None:
            with canvas.fill(color=colours["food"]):
                squares([self.food], gap)
        with canvas.fill(color=colours["body"]):
            squares(self.snake[1:], gap)
        with canvas.fill(color=colours["head"]):
            squares(self.snake[:1], gap)
        if self.state == "paused":
            centre_x, centre_y = width / 2, height / 2
            with canvas.fill(color=PAUSE_BARS):
                canvas.rect(
                    centre_x - cell * 1.6, centre_y - cell * 2, cell * 1.2, cell * 4
                )
                canvas.rect(
                    centre_x + cell * 0.4, centre_y - cell * 2, cell * 1.2, cell * 4
                )
        self.canvas.redraw()


# ---------- MyPyStub integration ----------


def open_game(app, window, on_exit):
    game = SnakeGame(app, window, on_exit)
    window.title = "Snake"
    window.content = game.build()
    return game


def startup_into(app, ev):
    """Runs on the app's loop: push the game onto the main window."""
    window = app.main_window
    if window.content:
        if not hasattr(window, "content_stack"):
            window.content_stack = []
        window.content_stack.append((window.title, window.content))

    def leave():
        type(app).unstack_from(app)
        ev.set()

    open_game(app, window, leave)
    if not window.visible:
        window.show()


def standalone_startup(app, **kwargs):
    """Used when there is no host app: this script owns the whole Toga app.

    Toga has made the main window already; this gives it the game.
    """
    game = SnakeGame(app, app.main_window, app.request_exit)
    return game.build()


def main():
    app = toga.App.app
    if app:
        # Inside MyPyStub: stack onto its loop and hold the script open
        # until Back returns to the launcher.
        import threading

        ev = threading.Event()
        if app.loop:
            app.loop.call_soon(lambda: startup_into(app, ev))
        else:
            startup_into(app, ev)
        ev.wait()
    else:
        toga.App(
            "Snake",
            "com.example.snake",
            startup=standalone_startup,
        ).main_loop()


# Do NOT call main() at module level: MyPyStub's launcher calls main() itself.
if __name__ == "__main__":
    main()
