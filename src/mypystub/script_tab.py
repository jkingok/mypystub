"""The Script view: a run's output, its errors, and where input() is answered.

One :class:`ScriptTab` holds the widgets a script's run is shown in:

- the output pane (``print_text``) and the errors pane beside or below it,
  shown when something is written to stderr, with Hide;
- the ``input()`` and ``getpass()`` questions, each a prompt and a field,
  which take the activity row's place at the bottom while they wait;
- the activity row ("Running …" and how the run ended);

and :meth:`ScriptTab.runner` makes the :class:`hooks.ScriptRunner` that sends
a run's output and questions here.

It needs only the standard library and Toga (and ``hooks``, which sits beside
it), so an app made from the project template runs it unchanged. Where the
``togax_jkingok`` widgets can be imported, the panes turn with the screen and
the view keeps clear of the notch and the keyboard; elsewhere plain Toga boxes
stand in for them.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import toga

from . import hooks

log = logging.getLogger(__name__)


def make_console() -> Any | None:
    """A new Experimental Console (toga-console) for the Script tab, or None.

    toga-console is optional: without it, or if it fails to load, the usual
    output is shown instead, and the reason is logged.
    """
    try:
        from toga_console import Console  # pyright: ignore[reportMissingImports]
    except ImportError as error:
        log.info(f"Console unavailable, using the usual output: {error}")
        return None
    return Console(readonly=True, follow=True, flex=1)


# Text colour for a run's stderr: an orange that reads as a warning, with
# enough contrast on both the light and the dark background
WARNING_COLOUR = "#d9480f"
# Seconds a closed question waits for the next one before its keyboard goes
KEYBOARD_GRACE = 0.3


class _Activity(toga.Box):
    """A spinner and a line of text (stands in for togax's LabelledActivity)."""

    def __init__(self, **kwargs: Any) -> None:
        """Make the indicator and its label; `kwargs` style the row."""
        self.activity = toga.ActivityIndicator()
        self.text = toga.Label("", flex=1)
        super().__init__(direction="row", children=[self.activity, self.text], **kwargs)

    def update(self, value: str = "", on: bool = True) -> None:
        """Show `value`, with the indicator spinning while `on`."""
        if on:
            self.activity.start()
        else:
            self.activity.stop()
        self.text.text = value


def _pair(first: toga.Widget, second: toga.Widget, **kwargs: Any) -> toga.Box:
    """Two widgets one above the other (stands in for togax's OrientationBox)."""
    kwargs.pop("equal", None)
    return toga.Column(children=[first, second], **kwargs)


try:  # the richer widgets, where they're installed (as in MyPyStub)
    from togax_jkingok import (  # pyright: ignore[reportMissingImports]
        LabelledActivity as Activity,
    )
    from togax_jkingok import OrientationBox as Pair
    from togax_jkingok import SafeColumn as ViewBox
except ImportError:
    Activity = _Activity  # type: ignore[assignment, misc]
    Pair = _pair  # type: ignore[assignment]
    ViewBox = toga.Column  # type: ignore[assignment, misc]


class ScriptTab:
    """The widgets a run is shown in, and how they change while it runs."""

    def __init__(
        self,
        app: toga.App,
        close_keyboard: Callable[[toga.Widget], None] | None = None,
        splash: toga.Widget | None = None,
        console_wanted: Callable[[], bool] | None = None,
    ) -> None:
        """Make the widgets for `app`.

        `close_keyboard` puts the keyboard away from a field (see
        :meth:`close_keyboard_soon`); without it, nothing does. `splash`, if
        given, sits above the output before anything is shown. `console_wanted`
        says at the start of each run whether to use the Experimental Console;
        left out, it is used whenever toga-console is installed (the default
        for a project, which has no switch).
        """
        self.app = app
        self.close_keyboard = close_keyboard
        self.console_wanted = console_wanted or (lambda: True)
        self.console_widget: Any = None
        self.active_runner: hooks.ScriptRunner | None = None
        # The question goes above its field, or beside it in landscape, where
        # a small phone has about 40 points above the keyboard (#305)
        self.input_prompt = toga.Label("Input", margin=(0, 4))
        self.input_text = toga.TextInput(flex=1)
        self.input_box = Pair(
            self.input_prompt,
            self.input_text,
            equal=False,
            text_align="center",
            align_items="center",
        )
        # getpass() asks here instead, so the password isn't shown (#121)
        self.password_prompt = toga.Label("Password", margin=(0, 4))
        self.password_text = toga.PasswordInput(flex=1)
        self.password_box = Pair(
            self.password_prompt,
            self.password_text,
            equal=False,
            text_align="center",
            align_items="center",
        )
        # A MultilineTextInput scrolls itself. Inside a ScrollContainer it is laid
        # out at its own small minimum, and isn't laid out again when the space
        # changes (rotation, the error pane hiding), so it fills the box itself.
        self.print_text = toga.MultilineTextInput(readonly=True, flex=1)
        # The run's stderr, shown beside or below its output (#119). It's
        # hidden until something is written to it, and Hide hides it again
        # until the next write.
        self.error_text = toga.MultilineTextInput(
            readonly=True, color=WARNING_COLOUR, flex=1
        )
        self.error_pane = toga.Column(
            display="none",
            children=[
                toga.Row(
                    align_items="center",
                    margin=(0, 4),
                    children=[
                        toga.Label("Errors and warnings", color=WARNING_COLOUR, flex=1),
                        toga.Button("Hide", on_press=self.hide_errors),
                    ],
                ),
                self.error_text,
            ],
        )
        self.output = Pair(self.print_text, self.error_pane, flex=1)
        self.activity = Activity()
        self.splash = splash
        # The last row is the activity, or input()'s or getpass()'s question
        # while one is asked (see toggle_box). Where it can, the box keeps
        # that row above the keyboard.
        children = [self.output, self.activity]
        if splash is not None:
            children.insert(0, splash)
        self.box = ViewBox(children=children)

    def runner(self, **kwargs: Any) -> hooks.ScriptRunner:
        """A ScriptRunner showing its run here; `kwargs` add to its options."""
        self.active_runner = hooks.ScriptRunner(
            self.app,
            self.input_prompt,
            self.input_text,
            self.print_text,
            self.toggle_input,
            self.toggle_print,
            on_error_output=self.show_error_output,
            password_label=self.password_prompt,
            password_field=self.password_text,
            toggle_password=self.toggle_password,
            **kwargs,
        )
        return self.active_runner

    def choose_output(self) -> None:
        """At the start of a run: the console or the usual output, emptied.

        The choice is made per run, so a Setup switch takes effect from the next
        one. If toga-console can't be loaded, the usual output is used.
        """
        wanted = None
        if self.console_wanted():
            if self.console_widget is None:
                self.console_widget = make_console()
            wanted = self.console_widget
        shown = wanted if wanted is not None else self.print_text
        current = self.output.children[0]
        if current is not shown:
            self.output.replace(current, shown)
            shown.style.flex = 1
        if self.active_runner is not None:
            self.active_runner.console = wanted
        if wanted is not None:
            wanted.clear()
            wanted.readonly = True
        self.print_text.value = ""

    def toggle_input(self, on: bool) -> None:
        """Show or hide the field that input() asks with."""
        self.toggle_box(self.input_box, on)

    def toggle_password(self, on: bool) -> None:
        """Show or hide the password field that getpass() asks with."""
        self.toggle_box(self.password_box, on)

    def toggle_box(self, box: toga.Box, on: bool) -> None:
        """Swap `box` (input's or getpass's) in for the activity row, or back.

        The question goes at the bottom, under the output it follows, as at a
        terminal. While it asks, the activity row gives it its place, so the
        output keeps the room that is left.
        """
        view = self.box
        activity = self.activity
        if on:
            if box.parent is not None:
                return
            if activity.parent is not None:
                view.replace(activity, box)
            else:  # already asking with the other box
                view.add(box)
        elif box.parent is not None:
            field = self.password_text if box is self.password_box else self.input_text
            self.close_keyboard_soon(field)
            asking = [b for b in (self.input_box, self.password_box) if b.parent]
            if len(asking) == 1 and activity.parent is None:
                view.replace(box, activity)
            else:
                view.remove(box)

    def close_keyboard_soon(self, field: toga.Widget) -> None:
        """Put the keyboard away if no question follows the one just answered.

        Android leaves its keyboard up when the focused field is taken away,
        so it is closed here. A script that asks again straight away (a REPL's
        next prompt) keeps the keyboard up, so the check waits a moment for
        the next question first.
        """
        if self.close_keyboard is None:
            return
        close = self.close_keyboard

        def unless_asking() -> None:
            if self.input_box.parent is None and self.password_box.parent is None:
                close(field)

        loop = getattr(self.app, "loop", None)
        if loop is None:
            unless_asking()
        else:
            loop.call_later(KEYBOARD_GRACE, unless_asking)

    def toggle_print(self, on: bool) -> None:
        """Give the output pane the room once there is output."""
        if on:
            if self.splash is not None:
                self.splash.style.flex = 0
            self.output.style.flex = 1

    def show_error_output(self, text: str) -> None:
        """Add a run's stderr text, showing the pane if it was hidden."""
        self.error_text.value += text
        self.error_pane.style.display = "pack"
        self.toggle_print(True)

    def hide_errors(self, widget: toga.Widget | None = None, **kwargs: Any) -> None:
        """Hide the stderr pane until something is next written to it."""
        self.error_pane.style.display = "none"

    def clear(self) -> None:
        """Empty the panes for a new run."""
        self.print_text.value = ""
        self.error_text.value = ""
        self.error_pane.style.display = "none"
