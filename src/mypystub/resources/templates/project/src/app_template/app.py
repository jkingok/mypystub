"""App Template: your app. Change ``build`` to make it yours.

``main()`` works the same in MyPyStub, in ``briefcase dev`` and as a built app.
It takes over the window. Where something can take the window back (MyPyStub's
launcher keeps a ``content_stack`` on it), a Back button is shown; as an app of
its own there's nothing to go back to, so it is hidden.
"""

from typing import Any

import toga


def build(app: toga.App) -> None:
    """Make this app's screen. Runs on the app's main thread."""
    window = app.main_window
    assert isinstance(window, toga.MainWindow)
    stack: list[Any] | None = getattr(window, "content_stack", None)
    if stack is not None:
        stack.append((window.title, window.content))

    def back(widget: toga.Widget) -> None:
        if stack:
            window.title, window.content = stack.pop()

    count = toga.Label("Pressed 0 times")
    presses = [0]

    def press(widget: toga.Widget) -> None:
        presses[0] += 1
        count.text = f"Pressed {presses[0]} times"
        print(f"Pressed {presses[0]} times")

    window.title = "App Template"
    window.content = toga.Column(
        margin=8,
        children=[
            toga.Row(
                children=[
                    toga.Button(
                        "‹ Back",
                        on_press=back,
                        visibility="visible" if stack else "hidden",
                    )
                ]
            ),
            toga.Label("Hello from App Template!"),
            toga.Button("Press me", on_press=press),
            count,
        ],
    )


def main() -> None:
    """Show the app. Safe from any thread: the screen is made on the main one."""
    app = toga.App.app
    if app is None:
        print("Start it with `briefcase dev`, or run it in MyPyStub.")
        return
    app.loop.call_soon_threadsafe(build, app)


if __name__ == "__main__":
    main()
