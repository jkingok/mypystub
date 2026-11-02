"""Reusable Toga widgets that don't depend on the rest of the launcher.

Only Toga's public API and its style applicator are used, so these can move
into their own package, or be offered to Toga.
"""

from __future__ import annotations

from typing import Any

import toga
from toga.style.applicator import TogaApplicator


class _BoundsApplicator(TogaApplicator):
    """Toga's applicator, also telling its widget the size of the view it's in."""

    def set_bounds(self) -> None:
        """Place the widget and its children, then report its view's size."""
        super().set_bounds()
        root = self.widget.root
        self.widget.update_orientation(
            root.layout.content_width, root.layout.content_height
        )


class OrientationBox(toga.Box):
    """Two widgets sharing the space equally, arranged to suit the view's shape.

    When the view the box is in (the root of its layout, such as a tab's
    content) is portrait (width <= height), the widgets are one above the
    other; when it is landscape they are side by side. The view's size is
    checked after each layout, not the screen's or the window's, so the box
    also adapts inside split views and resizable windows. The view, not the
    box itself, decides, so a keyboard spacer or other sibling that squeezes
    the box doesn't flip it.

    A child hidden with ``display="none"`` takes no space, and the other then
    fills the box.
    """

    def __init__(self, first: toga.Widget, second: toga.Widget, **kwargs: Any) -> None:
        """Hold `first` (top or left) and `second` (bottom or right)."""
        super().__init__(children=[first, second], direction="column", **kwargs)
        first.style.flex = 1
        second.style.flex = 1
        self.applicator = _BoundsApplicator()

    @property
    def portrait(self) -> bool:
        """Whether the widgets are currently stacked top to bottom."""
        return self.style.direction == "column"

    def update_orientation(self, width: float, height: float) -> None:
        """Arrange the widgets for a box `width` by `height` points in size.

        Called after every layout. A change of direction needs another layout,
        which is queued on the app's loop rather than started from inside the
        current one. A zero size (not laid out yet) is ignored.
        """
        if width <= 0 or height <= 0:
            return
        direction = "column" if width <= height else "row"
        if direction == self.style.direction:
            return
        app = toga.App.app
        if app is not None and getattr(app, "loop", None) is not None:
            app.loop.call_soon(self._set_direction, direction)
        else:
            self._set_direction(direction)

    def _set_direction(self, direction: str) -> None:
        self.style.direction = direction
