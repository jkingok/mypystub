"""Take over the screen two levels deep; the run ends back at the launcher."""

from typing import Any, cast

import toga


def show_level(app: toga.App, level: int) -> None:
    """Push the current screen and show `level`. Runs on the app's main thread."""
    window = app.main_window
    assert isinstance(window, toga.MainWindow)
    # The launcher's stack of screens. Each level pushes the screen it covers and
    # pops it on Back; the run ends when the launcher's own screen is popped.
    stack: list[tuple[str, toga.Widget]] = cast(Any, window).content_stack
    stack.append((window.title, window.content))

    def back(widget: toga.Widget) -> None:
        title, content = stack.pop()
        window.title = title
        window.content = content

    children: list[toga.Widget] = [toga.Label(f"This is level {level}.")]
    if level < 2:
        children.append(toga.Button("Deeper", on_press=lambda w: show_level(app, 2)))
    children.append(toga.Button("Back", on_press=back))

    window.title = f"Level {level}"
    window.content = toga.Box(children=children, direction="column", margin=10)


def main() -> None:
    """Ask the app's main thread to show the first level."""
    app = toga.App.app
    if app is None:
        print("No app running?")
        return
    # Scripts run on a background thread; widgets must change on the main thread
    app.loop.call_soon_threadsafe(show_level, app, 1)


if __name__ == "__main__":
    main()
