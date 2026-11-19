"""Android's window insets, for SafeArea.

Android doesn't resize the window for the keyboard in the way Toga needs, so
the keyboard covers the bottom of the app. It does report how much of the window
the keyboard, the system bars and the display cutout take, to any view that
asks: a listener set on the view with ``setOnApplyWindowInsetsListener`` is
called whenever those change. :func:`watch` sets one, and also notices the view
moving or resizing (a tab being switched to, rotation), which changes how much
of an inset it overlaps.

The listener is an interface, so Chaquopy gives it to Java through a dynamic
proxy. This module imports Java at its top, so it is only imported on Android.
"""

from collections.abc import Callable
from typing import Any

from android.view import (  # pyright: ignore[reportMissingImports]
    View,
    WindowInsets,
)
from java import (  # pyright: ignore[reportMissingImports]
    dynamic_proxy,
    jclass,
)

from .safe_area import AndroidMeasure, Insets

SDK_INT = jclass("android.os.Build$VERSION").SDK_INT
TYPE_IME_FIRST_SDK = 30  # WindowInsets.Type, and the insets it names, arrived here


class InsetsListener(dynamic_proxy(View.OnApplyWindowInsetsListener)):  # type: ignore[misc]
    """Android's callback for new insets."""

    def __init__(self, watcher: "InsetsWatcher") -> None:
        super().__init__()
        self.watcher = watcher

    def onApplyWindowInsets(self, view: Any, insets: Any) -> Any:
        """Android has new insets: remember them and report."""
        self.watcher.window_insets = insets
        self.watcher.report()
        return view.onApplyWindowInsets(insets)  # carry on as the view would


class LayoutListener(dynamic_proxy(View.OnLayoutChangeListener)):  # type: ignore[misc]
    """Android's callback for the view moving or changing size."""

    def __init__(self, watcher: "InsetsWatcher") -> None:
        super().__init__()
        self.watcher = watcher

    def onLayoutChange(
        self,
        view: Any,
        left: int,
        top: int,
        right: int,
        bottom: int,
        old_left: int,
        old_top: int,
        old_right: int,
        old_bottom: int,
    ) -> None:
        """The view moved or resized, which changes what it overlaps."""
        self.watcher.report()


class InsetsWatcher:
    """Reports a view's insets to `callback` when they or the view change."""

    def __init__(self, view: Any, callback: Callable[[AndroidMeasure, float], None]):
        self.view = view
        self.callback = callback
        self.window_insets: Any = None
        self.density = float(view.getResources().getDisplayMetrics().density)
        self.listeners = (InsetsListener(self), LayoutListener(self))

    def report(self) -> None:
        """Measure the view and its insets, and pass them on."""
        view, insets = self.view, self.window_insets
        root = view.getRootView()
        if insets is None or root is None:
            return
        x, y = layout_origin(view)
        measure = AndroidMeasure(
            system=system_insets(insets),
            keyboard=keyboard_height(insets),
            box=(x, y, float(view.getWidth()), float(view.getHeight())),
            window=(float(root.getWidth()), float(root.getHeight())),
        )
        try:
            self.callback(measure, self.density)
        except Exception as error:  # noqa: BLE001  (don't break Android's layout)
            print(f"Insets callback failed: {error}")


def layout_origin(view: Any) -> tuple[float, float]:
    """Where `view` is in its window's layout, in pixels, ignoring any pan.

    When the keyboard would cover the focused field, Android slides the whole
    window up to show it. getLocationInWindow includes that slide, which makes
    the view look higher than it is: padding it by less lets the keyboard cover
    more of it, so Android slides further, and the padding never settles. The
    layout positions don't move, so they are added up instead (less what a
    scrolling parent has scrolled by).
    """
    x = y = 0.0
    current = view
    while current is not None:
        x += current.getLeft()
        y += current.getTop()
        parent = current.getParent()
        if not isinstance(parent, View):
            break
        x -= parent.getScrollX()
        y -= parent.getScrollY()
        current = parent
    return x, y


def system_insets(insets: Any) -> Insets:
    """The system bars' and display cutout's insets, as the larger on each side."""
    if SDK_INT >= TYPE_IME_FIRST_SDK:
        kinds = WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()
        found = insets.getInsets(kinds)
        return Insets(found.top, found.right, found.bottom, found.left)
    return Insets(
        insets.getStableInsetTop(),
        insets.getStableInsetRight(),
        insets.getStableInsetBottom(),
        insets.getStableInsetLeft(),
    )


def keyboard_height(insets: Any) -> float:
    """How far up from the window's bottom edge the keyboard reaches."""
    if SDK_INT >= TYPE_IME_FIRST_SDK:
        return float(insets.getInsets(WindowInsets.Type.ime()).bottom)
    # Before Android 11 the system inset includes the keyboard (and the bar under it)
    return float(insets.getSystemWindowInsetBottom())


def watch(
    view: Any, callback: Callable[[AndroidMeasure, float], None]
) -> InsetsWatcher:
    """Call `callback(measure, density)` whenever `view`'s insets change.

    Returns the watcher, which the caller keeps for as long as it is wanted. Asks
    for a first report, which Android gives once the view is attached.
    """
    watcher = InsetsWatcher(view, callback)
    view.setOnApplyWindowInsetsListener(watcher.listeners[0])
    view.addOnLayoutChangeListener(watcher.listeners[1])
    view.requestApplyInsets()
    return watcher
