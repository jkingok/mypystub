"""SafeArea on Android: padding from the window insets Android reports (#290).

Chaquopy and the Android classes are replaced by stand-ins, so the arithmetic,
the wiring into SafeArea, and the listeners can all run on the desktop.
"""

from __future__ import annotations

import importlib
import sys
import types
from collections.abc import Iterator
from typing import Any

import pytest
import toga

from tests import support_ui  # noqa: F401 (selects the dummy backend)
from togax_jkingok import safe_area
from togax_jkingok.safe_area import (
    NO_INSETS,
    AndroidMeasure,
    Insets,
    SafeColumn,
    SafeRow,
    android_padding,
)

# A 1080x2400 phone at 2.625x density: status bar 63 px, navigation bar 126 px
WINDOW = (1080.0, 2400.0)
BARS = Insets(63, 0, 126, 0)
DENSITY = 2.625


def measure(
    box: tuple[float, float, float, float],
    keyboard: float = 126,
    system: Insets = BARS,
) -> AndroidMeasure:
    return AndroidMeasure(system, keyboard, box, WINDOW)


def test_a_tab_above_the_navigation_bar_needs_no_padding() -> None:
    """The framework already keeps it clear of both bars."""
    box = (0, 210, 1080, 2400 - 210 - 126 - 168)  # app bar above, tab bar below
    assert android_padding(measure(box), DENSITY) == (NO_INSETS, False)


def test_a_screen_reaching_the_window_edges_avoids_the_bars() -> None:
    box = (0, 0, 1080, 2400)
    insets, keyboard_up = android_padding(measure(box), DENSITY)
    assert insets == Insets(24, 0, 48, 0)  # 63/2.625 and 126/2.625, rounded up
    assert not keyboard_up


def test_the_keyboard_pads_what_it_covers() -> None:
    """A keyboard 1123 px tall: the tab's bottom 1123 - (126 + 168) px is under it."""
    box = (0, 210, 1080, 2400 - 210 - 126 - 168)
    insets, keyboard_up = android_padding(measure(box, keyboard=1123), DENSITY)
    assert keyboard_up
    assert insets == Insets(0, 0, round((1123 - 294) / DENSITY + 0.5), 0)


def test_a_keyboard_below_the_box_changes_nothing() -> None:
    box = (0, 210, 1080, 600)
    assert android_padding(measure(box, keyboard=1123), DENSITY) == (NO_INSETS, False)


def test_the_keyboard_can_be_ignored() -> None:
    box = (0, 0, 1080, 2400)
    insets, keyboard_up = android_padding(
        measure(box, keyboard=1123), DENSITY, keyboard=False
    )
    assert insets == Insets(24, 0, 48, 0) and not keyboard_up


def test_landscape_cutout_is_avoided_at_the_side() -> None:
    """A notch on the left of a landscape phone: the side it is on."""
    system = Insets(0, 0, 63, 126)
    box = (0, 0, 2400, 1080)
    insets, _ = android_padding(
        AndroidMeasure(system, 63, box, (2400.0, 1080.0)), DENSITY
    )
    assert insets == Insets(0, 0, 24, 48)


def test_a_box_a_pixel_past_the_window_edge_gets_no_padding() -> None:
    """Rounding can put a box 1 px wider than the window: no side padding."""
    box = (0, 210, 1081, 2400 - 210 - 126 - 168)
    assert android_padding(measure(box), DENSITY) == (NO_INSETS, False)


def test_a_view_not_laid_out_yet_has_no_insets() -> None:
    assert android_padding(measure((0, 0, 0, 0)), DENSITY) == (NO_INSETS, False)
    assert android_padding(measure((0, 0, 100, 100)), 0) == (NO_INSETS, False)


# SafeArea itself, with a stand-in for _android_insets


class Watcher:
    def __init__(self, view: Any, callback: Any) -> None:
        self.view, self.callback = view, callback


@pytest.fixture
def android(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    """The platform set to Android, with a recording _android_insets module."""
    module = types.ModuleType("togax_jkingok._android_insets")
    module.watch = Watcher  # type: ignore[attr-defined]
    from toga_dummy.widgets.box import Box

    monkeypatch.setattr(Box, "native", object(), raising=False)  # the Android view
    monkeypatch.setattr(toga.App, "app", None)  # no loop: changes apply at once
    monkeypatch.setattr(safe_area.sys, "platform", "android")
    monkeypatch.setitem(sys.modules, "togax_jkingok._android_insets", module)
    monkeypatch.setattr(
        sys.modules["togax_jkingok"], "_android_insets", module, raising=False
    )
    yield module


def test_the_box_watches_its_own_view(android: Any) -> None:
    area = SafeColumn(children=[toga.Label("hi")])
    assert isinstance(area._observer, Watcher)
    assert area._observer.view is area._impl.native


def test_new_insets_pad_the_content_and_are_reported(android: Any) -> None:
    seen: list[Insets] = []
    area = SafeColumn(
        children=[toga.Label("hi")],
        on_change=lambda box, insets: seen.append(insets),
    )
    area._observer.callback(measure((0, 0, 1080, 2400)), DENSITY)
    assert area.insets == Insets(24, 0, 48, 0)
    assert seen == [Insets(24, 0, 48, 0)]


def test_the_space_goes_on_the_content(android: Any) -> None:
    """Android's insets become the one content box's margin (SafeArea, #290)."""
    top, middle, bottom = (toga.Label(name) for name in ("top", "middle", "bottom"))
    area = SafeColumn(children=[top, middle, bottom])
    area._observer.callback(measure((0, 0, 1080, 2400)), DENSITY)
    assert area.insets == Insets(24, 0, 48, 0)
    content = area.content.style
    assert (content.margin_top, content.margin_bottom) == (24, 48)
    assert all(c.style.margin_top == c.style.margin_bottom == 0 for c in (top, bottom))


def test_a_row_gets_its_space_on_the_content_too(android: Any) -> None:
    system = Insets(0, 126, 63, 126)  # landscape: bars at the sides and bottom
    first, last = toga.Label("first"), toga.Label("last")
    area = SafeRow(children=[first, last])
    area._observer.callback(
        AndroidMeasure(system, 0, (0, 0, 2400, 1080), (2400.0, 1080.0)), DENSITY
    )
    content = area.content.style
    assert (content.margin_left, content.margin_right, content.margin_bottom) == (
        48,
        48,
        24,
    )
    assert first.style.margin_left == last.style.margin_right == 0


def test_the_keyboard_lets_scrolling_widgets_shrink(android: Any) -> None:
    text = toga.MultilineTextInput(readonly=True, flex=1)
    area = SafeColumn(children=[toga.Column(children=[text])])
    area._observer.callback(measure((0, 210, 1080, 1800), keyboard=1123), DENSITY)
    assert vars(text)["_MIN_HEIGHT"] == 0
    area._observer.callback(measure((0, 210, 1080, 1800)), DENSITY)
    assert "_MIN_HEIGHT" not in vars(text)


def test_without_keyboard_handling_only_the_bars_count(android: Any) -> None:
    area = SafeColumn(children=[toga.Label("hi")], keyboard=False)
    area._observer.callback(measure((0, 0, 1080, 2400), keyboard=1123), DENSITY)
    assert area.insets == Insets(24, 0, 48, 0)


def test_other_platforms_watch_nothing() -> None:
    assert SafeColumn(children=[toga.Label("hi")])._observer is None


# The Chaquopy side, with stand-ins for the Android classes


class FakeInsets:
    """android.graphics.Insets."""

    def __init__(self, left: int = 0, top: int = 0, right: int = 0, bottom: int = 0):
        self.left, self.top, self.right, self.bottom = left, top, right, bottom


class WindowInsets:
    """android.view.WindowInsets, as reported from Android 11."""

    class Type:
        @staticmethod
        def ime() -> int:
            return 8

        @staticmethod
        def systemBars() -> int:
            return 1

        @staticmethod
        def displayCutout() -> int:
            return 2

    def __init__(self, ime: int = 0) -> None:
        self.ime = ime

    def getInsets(self, kinds: int) -> FakeInsets:
        if kinds == 8:
            return FakeInsets(bottom=self.ime)
        assert kinds == 1 | 2  # bars and cutout together
        return FakeInsets(left=3, top=63, right=5, bottom=126)


class FakeView:
    """android.view.View, recording the listeners it is given."""

    class OnApplyWindowInsetsListener: ...

    class OnLayoutChangeListener: ...

    def __init__(self) -> None:
        self.apply: Any = None
        self.layout: Any = None
        self.requested = 0
        self.applied: list[Any] = []

    def getResources(self) -> Any:
        metrics = types.SimpleNamespace(density=DENSITY)
        return types.SimpleNamespace(getDisplayMetrics=lambda: metrics)

    def setOnApplyWindowInsetsListener(self, listener: Any) -> None:
        self.apply = listener

    def addOnLayoutChangeListener(self, listener: Any) -> None:
        self.layout = listener

    def requestApplyInsets(self) -> None:
        self.requested += 1

    def getRootView(self) -> Any:
        return types.SimpleNamespace(getWidth=lambda: 1080, getHeight=lambda: 2400)

    def getLeft(self) -> int:
        return 0

    def getTop(self) -> int:
        return 210

    def getParent(self) -> Any:
        return None  # nothing above it, as far as layout is concerned

    def getLocationInWindow(self, place: list[int]) -> None:
        raise AssertionError("this includes the pan; the layout position is used")

    def getWidth(self) -> int:
        return 1080

    def getHeight(self) -> int:
        return 1800

    def onApplyWindowInsets(self, insets: Any) -> Any:
        self.applied.append(insets)
        return insets


@pytest.fixture
def native(monkeypatch: pytest.MonkeyPatch) -> Iterator[Any]:
    java = types.ModuleType("java")
    java.dynamic_proxy = lambda *interfaces: object  # type: ignore[attr-defined]
    java.jarray = lambda kind: lambda size: [0] * size  # type: ignore[attr-defined]
    java.jint = int  # type: ignore[attr-defined]
    java.jclass = lambda name: types.SimpleNamespace(SDK_INT=34)  # type: ignore[attr-defined]
    android = types.ModuleType("android")
    view = types.ModuleType("android.view")
    view.View = FakeView  # type: ignore[attr-defined]
    view.WindowInsets = WindowInsets  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "java", java)
    monkeypatch.setitem(sys.modules, "android", android)
    monkeypatch.setitem(sys.modules, "android.view", view)
    monkeypatch.delitem(sys.modules, "togax_jkingok._android_insets", raising=False)
    module = importlib.import_module("togax_jkingok._android_insets")
    yield module
    sys.modules.pop("togax_jkingok._android_insets", None)


def test_watching_sets_both_listeners_and_asks_for_insets(native: Any) -> None:
    view = FakeView()
    native.watch(view, lambda *args: None)
    assert view.apply is not None and view.layout is not None
    assert view.requested == 1


def test_new_insets_are_measured_and_passed_on(native: Any) -> None:
    view, got = FakeView(), []
    native.watch(view, lambda m, density: got.append((m, density)))
    insets = WindowInsets(ime=1123)
    assert view.apply.onApplyWindowInsets(view, insets) is insets
    assert view.applied == [insets]  # the view carries on as it would have
    ((m, density),) = got
    assert density == DENSITY
    assert m.system == Insets(63, 5, 126, 3)
    assert m.keyboard == 1123
    assert m.box == (0.0, 210.0, 1080.0, 1800.0)
    assert m.window == (1080.0, 2400.0)


def test_a_layout_change_reports_again_with_the_last_insets(native: Any) -> None:
    view, got = FakeView(), []
    native.watch(view, lambda m, density: got.append(m))
    view.layout.onLayoutChange(view, 0, 0, 1, 1, 0, 0, 1, 1)
    assert got == []  # no insets yet
    view.apply.onApplyWindowInsets(view, WindowInsets())
    view.layout.onLayoutChange(view, 0, 0, 1, 1, 0, 0, 1, 1)
    assert len(got) == 2


def test_a_failing_callback_does_not_break_layout(
    native: Any, caplog: pytest.LogCaptureFixture
) -> None:
    def broken(m: Any, density: float) -> None:
        raise RuntimeError("oops")

    view = FakeView()
    native.watch(view, broken)
    view.apply.onApplyWindowInsets(view, WindowInsets())
    assert "Insets callback failed: oops" in caplog.text


def test_before_android_11_the_older_insets_are_used(
    native: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    class Old:
        def getStableInsetTop(self) -> int:
            return 63

        def getStableInsetRight(self) -> int:
            return 0

        def getStableInsetBottom(self) -> int:
            return 126

        def getStableInsetLeft(self) -> int:
            return 0

        def getSystemWindowInsetBottom(self) -> int:
            return 1123

    monkeypatch.setattr(native, "SDK_INT", 29)
    assert native.system_insets(Old()) == Insets(63, 0, 126, 0)
    assert native.keyboard_height(Old()) == 1123


def test_the_layout_position_adds_up_the_parents_and_their_scrolling(
    native: Any,
) -> None:
    """Android's pan isn't a view scroll, so it can't move this (it loops if it does)."""

    class Parent(FakeView):
        def __init__(self, left: int, top: int, scroll_y: int, up: Any) -> None:
            super().__init__()
            self.left, self.top, self.scroll_y, self.up = left, top, scroll_y, up

        def getLeft(self) -> int:
            return self.left

        def getTop(self) -> int:
            return self.top

        def getScrollX(self) -> int:
            return 0

        def getScrollY(self) -> int:
            return self.scroll_y

        def getParent(self) -> Any:
            return self.up

    window = Parent(0, 0, 0, object())  # its parent is the ViewRoot, not a View
    scrolled = Parent(10, 100, 30, window)
    view = Parent(5, 50, 0, scrolled)
    assert native.layout_origin(view) == (5 + 10, 50 + 100 - 30)
