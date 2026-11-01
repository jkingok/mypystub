"""Take over the screen, then hand it back with a Back button."""

from typing import Any, cast

import toga


def take_over(app: toga.App) -> None:
    """Swap in our own screen. Runs on the app's main thread."""
    window = app.main_window
    assert isinstance(window, toga.MainWindow)
    # The launcher's stack of screens: push its screen, so the run ends when
    # it's popped again
    stack: list[tuple[str, toga.Widget]] = cast(Any, window).content_stack
    stack.append((window.title, window.content))

    def back(widget: toga.Widget) -> None:
        # Restoring the launcher's title and content hands the screen back.
        # A second press pops nothing more, so a double tap is harmless.
        title, content = stack.pop()
        window.title = title
        window.content = content

    window.title = "Takeover"
    window.content = toga.Box(
        children=[
            toga.Label("This screen belongs to the prototype."),
            toga.Button("Back", on_press=back),
        ],
        direction="column",
        margin=10,
    )


def main() -> None:
    """Ask the app's main thread to show the takeover screen."""
    app = toga.App.app
    if app is None:
        print("No app running?")
        return
    # Scripts run on a background thread; widgets must change on the main thread
    app.loop.call_soon_threadsafe(take_over, app)
    print("Took over the screen; press Back to return.")


if __name__ == "__main__":
    main()
