"""Collapsible: a section whose heading is a switch that shows or hides it.

Toga has no disclosure widget, and a Switch is native on every platform, so the
heading is a bold Switch with the section's title. Its body is hidden while the
switch is off, and also while the section has nothing to show
(:attr:`Collapsible.has_content`), so an empty section is just its heading.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import toga
from toga.handlers import wrapped_handler

# Space around the heading: a little above it and at the sides, none below, so
# the body sits right under its title
HEADING_MARGIN = (8, 8, 0, 8)


class Collapsible(toga.Box):
    """A heading switch and the body of widgets it shows or hides."""

    def __init__(
        self,
        title: str,
        children: Iterable[toga.Widget] = (),
        *,
        open: bool = False,
        has_content: bool = True,
        on_change: Any = None,
        **kwargs: Any,
    ) -> None:
        """A section titled `title` holding `children`, shown while `open`.

        `on_change` is called with the section after it opens or closes.
        `kwargs` style the whole section.
        """
        self._has_content = has_content
        self._on_change: Any = None
        self.toggle = toga.Switch(
            title,
            value=open,
            on_change=self._toggled,
            margin=HEADING_MARGIN,
            font_weight="bold",
        )
        self.body = toga.Column(children=list(children))
        super().__init__(
            children=[self.toggle, self.body], direction="column", **kwargs
        )
        self.on_change = on_change
        self._show()

    @property
    def title(self) -> str:
        """The heading's text."""
        return str(self.toggle.text)

    @title.setter
    def title(self, value: str) -> None:
        self.toggle.text = value

    @property
    def open(self) -> bool:
        """Whether the section is open (its switch is on)."""
        return bool(self.toggle.value)

    @open.setter
    def open(self, value: bool) -> None:
        self.toggle.value = value  # the switch's on_change shows or hides it

    @property
    def has_content(self) -> bool:
        """Whether the body has anything to show; if not it stays hidden."""
        return self._has_content

    @has_content.setter
    def has_content(self, value: bool) -> None:
        self._has_content = value
        self._show()

    @property
    def on_change(self) -> Any:
        """Called with the section after it opens or closes."""
        return self._on_change

    @on_change.setter
    def on_change(self, handler: Any) -> None:
        self._on_change = wrapped_handler(self, handler)

    @property
    def shown(self) -> bool:
        """Whether the body is showing: open, with something to show."""
        return self.open and self._has_content

    def _show(self) -> None:
        self.body.style.display = "pack" if self.shown else "none"

    def _toggled(self, widget: toga.Switch, **kwargs: Any) -> None:
        self._show()
        if self._on_change is not None:
            self._on_change()
