"""GUI entry point: take over the window, then hand it back."""

from typing import Any, cast

import toga


def take_over(app: toga.App) -> None:
    """Swap in our own screen, pushing the old one onto the content stack."""
    window = app.main_window
    assert isinstance(window, toga.MainWindow)
    stack: list[tuple[str, toga.Widget]] = cast(Any, window).content_stack
    stack.append((window.title, window.content))

    def back(widget: toga.Widget) -> None:
        window.title, window.content = stack.pop()

    window.title = "Two Tools"
    window.content = toga.Box(
        children=[
            toga.Label("A GUI entry point, sharing the launcher's window."),
            toga.Button("Back", on_press=back),
        ],
        direction="column",
        margin=10,
    )


def show() -> None:
    """Ask the app's main thread to show the window."""
    app = toga.App.app
    if app is None:
        print("No app running?")
        return
    app.loop.call_soon_threadsafe(take_over, app)


if __name__ == "__main__":
    show()
