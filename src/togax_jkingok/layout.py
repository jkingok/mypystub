"""Layout helpers: lay content out again when Toga doesn't do it by itself.

Toga lays a scroll view's content out to the size it had at the time, and some
backends don't do it again after rotation, a split view, or a tab that wasn't
showing. These helpers ask for the layout again when it can have changed.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import toga


def refresh_on_new_width(container: Any, refresh: Callable[[], None]) -> None:
    """Call `refresh` when a native container gets a new width.

    A scroll view in a tab that hasn't been shown lays its content out before it
    has a width, and Toga's refreshes on showing the tab can run before the
    width arrives too. Nothing lays the content out after that, so it stays at
    its minimum width: flex can't help, as the content's own width is what's
    too small. Waiting for the native layout, not a timer, also covers rotation.
    Only a change of width refreshes, as a refresh causes a native layout.
    """
    seen = 0.0

    def laid_out(_container: Any) -> None:
        nonlocal seen
        width = container.width
        if width and width != seen:
            seen = width
            refresh()

    container.on_native_layout = laid_out


def relayout(widget: Any) -> None:
    """Lay `widget` out again, and the content of every scroll view inside it.

    A scroll view lays its content out to its own size, and some backends don't
    do it again when that size changes, or for a tab that wasn't showing when
    the window changed shape. Refreshing is cheap and changes nothing that is
    already right. Nothing happens for None.
    """
    if widget is None:
        return
    if isinstance(widget, toga.Widget):
        widget.refresh()
    pending = [widget]
    while pending:
        current = pending.pop()
        if isinstance(current, toga.ScrollContainer) and current.content is not None:
            current.content.refresh()
            pending.append(current.content)
        pending.extend(getattr(current, "children", None) or [])


def relayout_on_resize(window: Any) -> None:
    """Lay the window's content out again whenever the window changes size.

    Rotation, split view and resizable windows all arrive as a resize. Any
    `on_resize` handler already set is still called, first. Toga can report a
    resize after every native layout pass (Android does), so only a change of
    size does anything.
    """
    if getattr(window, "_relayout_on_resize", False):
        return  # already watching (the launcher's content can be built again)
    previous = window.on_resize  # Toga's wrapper: it passes the window itself
    seen: list[tuple[int, int]] = []

    def resized(window: Any, **kwargs: Any) -> None:
        if previous is not None:
            previous(**kwargs)
        size = tuple(window.size)
        if seen and seen[-1] == size:
            return
        seen[:] = [size]
        relayout(window.content)
        tabs = window.content
        if isinstance(tabs, toga.OptionContainer):
            relayout(tabs.current_tab.content if tabs.current_tab else None)

    window.on_resize = resized
    window._relayout_on_resize = True
