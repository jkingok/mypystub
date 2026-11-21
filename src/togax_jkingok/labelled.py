"""Small widgets that pair a control with a label beside it."""

from __future__ import annotations

from typing import Any

import toga


class LabelledProgress(toga.Box):
    """A progress bar with its count beside it: "3/10", or "30%" out of 100.

    With no limit the bar is indeterminate and the label is empty.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Make the bar and its label; `kwargs` style the row."""
        self.bar = toga.ProgressBar(flex=1)
        self.text = toga.Label("")
        super().__init__(direction="row", children=[self.bar, self.text], **kwargs)

    def start(self, limit: int = 0) -> None:
        """Start from zero, counting up to `limit` (0 for indeterminate)."""
        self.bar.max = limit if limit > 0 else None
        self.bar.start()
        self.update(0)

    def update(self, value: int) -> None:
        """Show `value` on the bar and in the label."""
        if self.bar.max:
            if self.bar.max == 100:
                self.text.text = f"{value}%"
            else:
                # Toga keeps the limit as a float; show 10, not 10.0
                self.text.text = f"{value}/{self.bar.max:g}"
        else:
            self.text.text = ""
        self.bar.value = value

    def stop(self) -> None:
        """Stop, showing the bar full if it had a limit."""
        if self.bar.max:
            self.update(int(self.bar.max))
        self.bar.stop()


class LabelledActivity(toga.Box):
    """An activity indicator with a line of status text, and a count when known.

    While the work's size is unknown only the indicator spins. Once it is known
    (:meth:`count`), a progress bar with "3/10" appears under the text, and
    goes again when the activity stops. The text and the bar share a column
    beside the indicator, so both get the row's full width on a narrow phone.
    """

    def __init__(self, **kwargs: Any) -> None:
        """Make the indicator, its label and its (hidden) count; `kwargs` style it."""
        self.activity = toga.ActivityIndicator()
        self.text = toga.Label("")
        self.progress = LabelledProgress(display="none")
        self.column = toga.Column(flex=1, children=[self.text, self.progress])
        super().__init__(
            direction="row",
            children=[self.activity, self.column],
            **kwargs,
        )

    @property
    def counting(self) -> bool:
        """Whether the count is showing."""
        return self.progress.style.display != "none"

    def update(self, value: str = "", on: bool = True) -> None:
        """Show `value`, with the indicator spinning while `on`.

        Stopping (`on` False) also takes the count away.
        """
        if on:
            self.activity.start()
        else:
            self.activity.stop()
            self.stop_count()
        self.text.text = value

    def count(self, done: int, total: int) -> None:
        """Show `done` of `total` steps; a new `total` starts the bar again."""
        if total <= 0:
            self.stop_count()
            return
        if not self.counting or self.progress.bar.max != total:
            self.progress.start(total)
            self.progress.style.display = "pack"
        self.progress.update(min(done, total))

    def stop_count(self) -> None:
        """Hide the count."""
        if self.counting:
            self.progress.stop()
            self.progress.style.display = "none"


class LabelledSelection(toga.Box):
    """A label and a Selection on one row: "Label: [choice]".

    `kwargs` go to the Selection (`items`, `value`, `on_change`, ...).
    """

    def __init__(self, label_text: str, **kwargs: Any) -> None:
        """Label the Selection with `label_text`."""
        self.selection = toga.Selection(flex=1, **kwargs)
        super().__init__(
            direction="row",
            align_items="center",
            children=[toga.Label(label_text + ": "), self.selection],
        )

    @property
    def value(self) -> Any:
        """The selected item."""
        return self.selection.value
