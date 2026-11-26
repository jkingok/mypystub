"""A Box that keeps its children clear of the notch, home indicator and keyboard.

Toga's iOS backend only moves a window's content below the navigation bar. The
rest of the screen's unsafe area is left to the app: the home indicator under
a screen pushed over the tabs, the notch or Dynamic Island beside a tab in
landscape, and the keyboard over whatever is at the bottom when a text field
has focus. :class:`SafeArea` is used in place of the Box that is a window's or
a tab's content, and moves its children in by exactly those amounts, updating
as they change.

On Android the same space comes from the window insets (system bars, display
cutout and keyboard) that Android reports to the box's view; see
:mod:`togax_jkingok._android_insets`. Android doesn't resize the window for the
keyboard, so without this it covers whatever is at the bottom.

Elsewhere it is a plain Box: desktop platforms lay windows out inside their
safe area and move content for the keyboard themselves.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

import toga

# What the platform reports and the padding applied, for diagnosing layouts
# (#305). Silent unless the app routes it: a print would land in whatever
# stdout is at the time, such as a running script's output.
log = logging.getLogger(__name__)


class Insets(NamedTuple):
    """Space, in points, to keep clear on each side (whole points once worked out)."""

    top: float = 0
    right: float = 0
    bottom: float = 0
    left: float = 0


NO_INSETS = Insets()
# Seconds after a rotation to read the insets again (see _read_again_if_resized)
REREAD_DELAY = 0.5

# Platforms where SafeArea works out the padding itself
NATIVE = ("ios", "android")

# Widgets that scroll their own content, so they stay usable when they get
# less than Toga's usual 100 point minimum height
SCROLLING = (
    toga.MultilineTextInput,
    toga.WebView,
    toga.DetailedList,
    toga.ScrollContainer,
)


def scrolling_widgets(root: toga.Widget | None) -> list[toga.Widget]:
    """Flexible, self-scrolling widgets in `root`'s tree, `root` included.

    Only these can give up height when the keyboard leaves little room: one
    with flex 0 is laid out at its minimum, so shrinking that would hide it.
    A scroll container's own content isn't searched, as it scrolls with it.
    """
    found: list[toga.Widget] = []
    pending = [root] if root is not None else []
    while pending:
        widget = pending.pop()
        if isinstance(widget, SCROLLING):
            if widget.style.flex > 0:
                found.append(widget)
            continue
        pending.extend(getattr(widget, "children", None) or [])
    return found


def insets_for(
    safe: Insets, height: float, clear_height: float, keyboard: bool = True
) -> Insets:
    """The padding a box needs, from what UIKit reports about it.

    `safe` is the box's safeAreaInsets. `height` is the box's own height and
    `clear_height` how far down it the keyboard leaves free (the top of the
    keyboard, or the box's safe bottom when there is no keyboard over it). With
    `keyboard` False, or before the box has been laid out, the keyboard is
    ignored. Values are rounded up to whole points, so nothing is left a
    fraction under an edge.
    """

    def points(value: float) -> int:
        return max(0, int(-(-value // 1)))

    bottom = safe.bottom
    if keyboard and height > 0 and clear_height >= 0:
        bottom = max(bottom, height - clear_height)
    return Insets(
        points(safe.top), points(safe.right), points(bottom), points(safe.left)
    )


def window_share(window_safe: Insets, frame: tuple[float, ...]) -> Insets:
    """The part of the window's safe-area insets that falls on a view.

    `frame` is the view's frame in window coordinates and the window's size,
    ``(x, y, width, height, window_width, window_height)``. UIKit's own
    ``safeAreaInsets`` for a view inside a tab can come back as 0 at the sides
    in landscape (seen on iPhone 13 mini simulators, iOS 26.5 and 27.2, #305),
    though the view runs under the notch; the window's insets still say where
    the notch is.
    """
    if len(frame) < 6:
        return NO_INSETS
    x, y, width, height, window_width, window_height = frame[:6]
    bottom_edge = min(y + height, window_height)
    return Insets(
        max(0.0, window_safe.top - y),
        max(0.0, window_safe.right - (window_width - (x + width))),
        max(0.0, window_safe.bottom - (window_height - bottom_edge)),
        max(0.0, window_safe.left - x),
    )


def visible_height(height: float, frame: tuple[float, ...]) -> float:
    """How much of a view's `height` is inside its window (see window_share).

    The bottom padding is worked out from this, not from the view's whole
    height: when the padded content can't fit, Toga makes the box taller than
    its space, and padding from the taller box would make it taller again, a
    step at a time, without end (#305, landscape with the keyboard on a small
    phone).
    """
    if len(frame) < 6:
        return height
    _, y, _, _, _, window_height = frame[:6]
    return max(0.0, min(height, window_height - y))


def widest(*insets: Insets) -> Insets:
    """Side by side, the largest of each edge."""
    return Insets(*(max(edges) for edges in zip(*insets, strict=True)))


class AndroidMeasure(NamedTuple):
    """What Android reports about a view, in pixels.

    `system` is the window's system bar and display cutout insets (top, right,
    bottom, left), `keyboard` the keyboard's height from the window's bottom
    edge (this includes the navigation bar under it), `box` the view's left,
    top, width and height in the window, and `window` the window's width and
    height.
    """

    system: Insets
    keyboard: float
    box: tuple[float, float, float, float]
    window: tuple[float, float]


def android_padding(
    measure: AndroidMeasure, density: float, keyboard: bool = True
) -> tuple[Insets, bool]:
    """The padding a view needs on Android, and whether the keyboard sets it.

    Android reports insets for the whole window; a view only needs padding for
    the part of each inset it actually overlaps. A tab above the navigation bar
    has none of it to avoid, and a screen that reaches the window's edge has
    all of it. Pixels become Toga's units by dividing by `density`. With
    `keyboard` False the keyboard is ignored.
    """
    x, y, width, height = measure.box
    if width <= 0 or height <= 0 or density <= 0:
        return NO_INSETS, False
    system = measure.system
    # A box a pixel past the window's edge (rounding) has no gap, not a negative one
    gaps = Insets(
        *(
            max(0.0, gap)
            for gap in (
                y,
                measure.window[0] - (x + width),
                measure.window[1] - (y + height),
                x,
            )
        )
    )
    overlap = Insets(*(max(0.0, inset - gap) for inset, gap in zip(system, gaps)))
    covered = max(0.0, measure.keyboard - gaps.bottom) if keyboard else 0.0
    keyboard_up = covered > overlap.bottom + 1
    scaled = Insets(*(value / density for value in overlap))
    return (
        insets_for(scaled, height / density, (height - covered) / density),
        keyboard_up,
    )


# Style properties that arrange a box's children: they belong to the content
CONTENT_LAYOUT = ("direction", "align_items", "justify_content", "gap")


class SafeArea(toga.Box):
    """A Box whose children stay where they can be seen and tapped.

    Use it instead of the Box that is a window's or a tab's content; it takes
    the same arguments, with `direction` and the rest of the style as usual.
    On iOS and Android its children are moved in by the box's safe area
    (status and navigation bars, tab bars, the notch or Dynamic Island, the
    rounded corners and the home indicator, in whatever orientation) and,
    unless `keyboard` is False, by the part of the box the keyboard covers. A
    hardware keyboard's shortcut bar counts as keyboard too.

    Like a ScrollContainer, it has exactly one child of its own, `content`: a
    Box holding the children, laid out by the `direction`, `align_items`,
    `justify_content` and `gap` given here. The insets are that one child's
    margin, so which children there are, in what order, and which are hidden,
    is left to Toga. Children are managed as on a Box: :meth:`add`,
    :meth:`insert`, :meth:`remove`, :meth:`replace`, :meth:`clear` and
    :meth:`index` act on `content`, and a child's `parent` is `content`.
    (`children` itself is ``[content]``, as Toga's layout needs to see it.)
    `on_change` is called with the box and the new :class:`Insets` each time
    they change.

    While the keyboard is up, flexible widgets that scroll their own content
    (multiline text, web views, lists and scroll containers) may shrink below
    Toga's usual minimum height, so that a field and the controls around it
    still fit above the keyboard, as they have to in landscape on a phone.
    Read-only text views among them are scrolled to their last line.

    Only one SafeArea needs to be on the way to any widget: one inside another
    gets nothing more to add, as the outer one has already moved its children.
    """

    def __init__(
        self,
        id: str | None = None,
        style: Any = None,
        children: Iterable[toga.Widget] | None = None,
        *,
        keyboard: bool = True,
        on_change: Callable[[SafeArea, Insets], Any] | None = None,
        **kwargs: Any,
    ) -> None:
        """Create the box, as :class:`toga.Box` does.

        `keyboard` False keeps the children clear of the safe area only.
        """
        self.keyboard = keyboard
        self.on_change = on_change
        self._insets = NO_INSETS
        self._pending: tuple[Insets, bool] | None = None
        self._squeezed: list[toga.Widget] = []
        self._observer: Any = None  # the native object watching the box
        self._box_observer: Any = None  # iOS: a second one, for the box's size
        self._last_size: tuple[float, float] | None = None  # iOS: see native_changed
        # Squeezed text views' own top and bottom padding, by id, to put back
        self._paddings: dict[int, tuple[float, float]] = {}
        layout = {name: kwargs.pop(name) for name in CONTENT_LAYOUT if name in kwargs}
        given = [name for name in CONTENT_LAYOUT if style is not None and name in style]
        for name in given:
            layout.setdefault(name, getattr(style, name))
        # The one child: it fills the box, and the insets are its margin
        self.content = toga.Box(children=children, flex=1, **layout)
        # Positionally: the launcher never names widget ids (see test_ui_app_isolation)
        super().__init__(id, style, **kwargs)
        for name in given:  # arranging the children is the content's job
            del self.style[name]
        # A column, so the one child fills the box's height as well as its width
        self.style.direction = "column"
        toga.Box.add(self, self.content)
        if sys.platform == "ios":
            self._observe()
        elif sys.platform == "android":
            self._observe_android()

    @property
    def insets(self) -> Insets:
        """The space the children are kept clear by now."""
        return self._insets

    # A Box's ways of managing children, acting on the content

    def add(self, *children: toga.Widget) -> None:
        """Add children to the end, as Box does."""
        self.content.add(*children)

    def insert(self, index: int, child: toga.Widget) -> None:
        """Insert a child at `index`, as Box does."""
        self.content.insert(index, child)

    def remove(self, *children: toga.Widget) -> None:
        """Remove children, as Box does."""
        self.content.remove(*children)

    def replace(self, old_child: toga.Widget, new_child: toga.Widget) -> None:
        """Put `new_child` where `old_child` is, as Box does."""
        self.content.replace(old_child, new_child)

    def clear(self) -> None:
        """Remove every child, as Box does."""
        self.content.clear()

    def index(self, child: toga.Widget) -> int:
        """Where `child` is among the children, as Box says."""
        return self.content.index(child)

    def set_insets(self, insets: Insets, keyboard_up: bool = False) -> None:
        """Keep the children clear by `insets`; tell `on_change` if they changed.

        `keyboard_up` says the keyboard is what sets the bottom, so scrolling
        widgets may shrink (see the class); once it's down they get their
        usual minimum back.
        """
        self._pending = None
        self._squeeze(keyboard_up)
        if insets == self._insets:
            return
        self._insets = insets
        if sys.platform == "ios":
            self._native_no_adjustment(scrolling_widgets(self.content))
        self.content.style.margin = tuple(insets)
        log.debug(
            "%s padding applied: %s%s",
            self.describe(),
            tuple(insets),
            " (keyboard up)" if keyboard_up else "",
        )
        if self.on_change is not None:
            self.on_change(self, insets)

    def _squeeze(self, on: bool) -> None:
        """Let scrolling widgets shrink to nothing, or give them their minimum back."""
        if on == bool(self._squeezed):
            return
        if on:
            self._squeezed = scrolling_widgets(self.content)
            for widget in self._squeezed:
                widget._MIN_HEIGHT = 0  # pyright: ignore[reportAttributeAccessIssue]
            changed = self._squeezed
        else:
            changed, self._squeezed = self._squeezed, []
            for widget in changed:
                if "_MIN_HEIGHT" in vars(widget):
                    del widget._MIN_HEIGHT  # back to the class's
        outputs = [
            widget
            for widget in changed
            if isinstance(widget, toga.MultilineTextInput) and widget.readonly
        ]
        if sys.platform == "ios":
            self._native_padding(outputs, on)
        for widget in changed:
            rehint = getattr(widget._impl, "rehint", None)
            if rehint is not None:
                rehint()
        if changed:
            self.refresh()
        if on:
            self._show_newest(outputs)

    def _show_newest(self, views: list[toga.Widget]) -> None:
        """Scroll read-only text views to their last line once laid out again.

        A squeezed output pane may be a line or two high; what was just
        written, such as the reply to what was typed, is what should show.
        """
        if not views:
            return
        app = toga.App.app
        loop = getattr(app, "loop", None) if app is not None else None
        scroll = self._native_scroll if sys.platform == "ios" else _scroll_down
        if loop is None:
            scroll(views)
        else:
            loop.call_soon(scroll, views)

    # iOS

    @staticmethod
    def _native_no_adjustment(views: list[toga.Widget]) -> None:
        """Stop UIKit moving scrolling views' content in by the safe area too.

        The box has already moved them clear of it, so UIKit's own adjustment
        could only count it twice; and a tab first shown under iPadOS's
        floating tab bar was adjusted before the box moved it, which left its
        content scrolled up under the bar.
        """
        never = 2  # UIScrollViewContentInsetAdjustmentNever
        for view in views:
            native = view._impl.native
            native = getattr(native, "scrollView", None) or native  # a web view's
            if native.contentInsetAdjustmentBehavior != never:
                native.contentInsetAdjustmentBehavior = never

    def _native_padding(self, views: list[toga.Widget], squeezed: bool) -> None:
        """Drop a text view's top and bottom padding while it is squeezed.

        UITextView pads its text by 8 points above and below, which in a pane
        a line high would hide the line itself; the padding comes back with
        the keyboard gone.
        """
        from rubicon.objc import (  # pyright: ignore[reportMissingImports]
            UIEdgeInsetsMake,
        )

        for view in views:
            native = view._impl.native
            inset = _value(native.textContainerInset)
            if squeezed:
                self._paddings[id(view)] = (inset.top, inset.bottom)
                native.setTextContainerInset(
                    UIEdgeInsetsMake(0, inset.left, 0, inset.right)
                )
            elif (padding := self._paddings.pop(id(view), None)) is not None:
                native.setTextContainerInset(
                    UIEdgeInsetsMake(padding[0], inset.left, padding[1], inset.right)
                )

    def _native_scroll(self, views: list[toga.Widget]) -> None:
        """Show the end of each text view, once UIKit has given it its new size.

        UIKit applies Toga's new frames on its next layout pass, and Toga's
        constraints live on the window's container views, so the window is
        laid out first. The offset is set directly: scrollRangeToVisible
        leaves a view shorter than a line where it was. Output usually ends
        with a newline, and the empty line after it isn't what should show.
        """
        from rubicon.objc import CGPoint  # pyright: ignore[reportMissingImports]

        native = self._impl.native
        (_value(native.window) or native).layoutIfNeeded()
        for view in views:
            text = view._impl.native
            bottom = float(text.contentSize.height) - float(text.bounds.size.height)
            if str(view.value).endswith("\n"):  # an empty last line: show the one above
                font = _value(text.font)
                bottom -= float(font.lineHeight) if font is not None else 0.0
            text.setContentOffset(CGPoint(0, max(0.0, bottom)), animated=False)

    def _observe(self) -> None:
        """Lay two observer views over the box, so UIKit reports every change.

        One ends at the top of the keyboard, and is laid out again when the
        keyboard moves; the other fills the box, and is laid out again when the
        box changes size. Each alone misses changes: after a rotation with the
        keyboard up, Toga can resize the box after the keyboard has settled,
        which leaves the first one's size, and so its layout, unchanged.
        """
        from . import _ios_observer

        observer_class: Any = getattr(_ios_observer, "SafeAreaObserverView")  # noqa: B009

        native = self._impl.native
        bottoms = [
            native.keyboardLayoutGuide.topAnchor
            if self.keyboard
            else native.bottomAnchor,
            native.bottomAnchor,
        ]
        observers = []
        for bottom in bottoms:
            observer = observer_class.alloc().init()
            observer.owner = self
            observer.userInteractionEnabled = False
            observer.translatesAutoresizingMaskIntoConstraints = False
            native.insertSubview(observer, atIndex=0)
            for constraint in (
                observer.topAnchor.constraintEqualToAnchor(native.topAnchor),
                observer.leadingAnchor.constraintEqualToAnchor(native.leadingAnchor),
                observer.trailingAnchor.constraintEqualToAnchor(native.trailingAnchor),
                observer.bottomAnchor.constraintEqualToAnchor(bottom),
            ):
                constraint.setActive(True)
            observers.append(observer)
        # The first measures the keyboard; the second is only there to be told
        self._observer, self._box_observer = observers

    def native_changed(self) -> None:
        """UIKit laid the observer out: work out the padding again.

        Called from inside UIKit's layout pass, so a change is applied on the
        app's loop rather than by laying Toga out from in here.
        """
        native = self._impl.native
        reported = native.safeAreaInsets
        frame = self._frame_in_window(native)
        window = self._window_safe(native)
        safe = widest(
            Insets(reported.top, reported.right, reported.bottom, reported.left),
            window_share(window, frame),
        )
        height = visible_height(float(native.bounds.size.height), frame)
        clear = float(self._observer.frame.size.height)
        self._log_reading(
            "iOS",
            safe=(reported.top, reported.right, reported.bottom, reported.left),
            window=tuple(window),
            box=frame,
            clear=clear,
        )
        insets = insets_for(safe, height, clear, self.keyboard)
        keyboard_up = self.keyboard and height > 0 and height - clear > safe.bottom + 1
        self._schedule(insets, keyboard_up)
        self._read_again_if_resized(frame)

    def _read_again_if_resized(self, frame: tuple[float, ...]) -> None:
        """After a change of size (a rotation), read once more a moment later.

        The scene's reference window (see _ios_reference) turns a little after
        the app's own, so the first reading can still have the old insets,
        and nothing else lays the box out again once it has settled.
        """
        size = (frame[4], frame[5]) if len(frame) >= 6 else None
        if size is None or size == self._last_size:
            return
        self._last_size = size
        app = toga.App.app
        loop = getattr(app, "loop", None) if app is not None else None
        if loop is not None:
            loop.call_later(REREAD_DELAY, self.native_changed)

    def _observe_android(self) -> None:
        """Have Android tell this box when its insets or position change."""
        from . import _android_insets as native

        self._observer = native.watch(self._impl.native, self.android_changed)

    def android_changed(self, measure: AndroidMeasure, density: float) -> None:
        """Android reported new insets or a new position: pad again."""
        self._log_reading("Android", measure=tuple(measure), density=density)
        self._schedule(*android_padding(measure, density, self.keyboard))

    # Diagnostics (#305): the log says what the platform reported and what was
    # applied, once per change, so a device or simulator run shows where
    # padding goes missing.

    def describe(self) -> str:
        """A short name for this box in the log: its first child's type."""
        children = self.content.children
        return f"SafeArea[{type(children[0]).__name__ if children else 'empty'}]"

    def _log_reading(self, platform: str, **reading: Any) -> None:
        rounded = {name: _rounded(value) for name, value in reading.items()}
        if rounded == getattr(self, "_last_reading", None):
            return
        self._last_reading = rounded
        log.debug(
            "%s %s reading: %s",
            self.describe(),
            platform,
            ", ".join(f"{name}={value}" for name, value in rounded.items()),
        )

    @staticmethod
    def _window_safe(native: Any) -> Insets:
        """The safe-area insets of the view's window, or none before it has one.

        Toga's window can keep its portrait insets in landscape, so the
        insets of a window made for the same scene the current way are used
        when there are any (see _ios_reference).
        """
        from . import _ios_reference

        try:
            window = _value(native.window)
            if window is None:
                return NO_INSETS
            scene = _ios_reference.scene_insets(window)
            if scene is not None:
                return Insets(*scene)
            safe = window.safeAreaInsets
            return Insets(safe.top, safe.right, safe.bottom, safe.left)
        except Exception:  # noqa: BLE001  (a reading must never break layout)
            return NO_INSETS

    @staticmethod
    def _frame_in_window(native: Any) -> tuple[float, ...]:
        """The view's frame in its window's coordinates, and the window's size."""
        try:
            frame = native.convertRect(native.bounds, toView=None)
            window = _value(native.window)
            size = window.bounds.size if window is not None else frame.size
            return (
                float(frame.origin.x),
                float(frame.origin.y),
                float(frame.size.width),
                float(frame.size.height),
                float(size.width),
                float(size.height),
            )
        except Exception:  # noqa: BLE001  (diagnostics must never break layout)
            return ()

    def _schedule(self, insets: Insets, keyboard_up: bool) -> None:
        """Apply new padding on the app's loop, not from inside the native layout."""
        wanted = (insets, keyboard_up)
        if wanted == (self._pending or (self._insets, bool(self._squeezed))):
            return
        self._pending = wanted
        app = toga.App.app
        loop = getattr(app, "loop", None) if app is not None else None
        if loop is None:
            self.set_insets(*wanted)
        else:
            loop.call_soon(self._apply_pending)

    def _apply_pending(self) -> None:
        if self._pending is not None:
            self.set_insets(*self._pending)


def SafeRow(*args: Any, **kwargs: Any) -> SafeArea:
    """Shorthand for :class:`SafeArea` with its direction set to "row"."""
    return SafeArea(*args, direction="row", **kwargs)


def SafeColumn(*args: Any, **kwargs: Any) -> SafeArea:
    """Shorthand for :class:`SafeArea` with its direction set to "column"."""
    return SafeArea(*args, direction="column", **kwargs)


def _scroll_down(views: list[toga.Widget]) -> None:
    """Scroll each text view to its end, through Toga, where it can."""
    for view in views:
        scroll = getattr(view, "scroll_to_bottom", None)
        if scroll is not None:
            scroll()


def _rounded(value: Any) -> Any:
    """Numbers to one decimal place, through nested tuples, for the log."""
    if isinstance(value, tuple):
        return tuple(_rounded(item) for item in value)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 1)
    return value


def _value(attribute: Any) -> Any:
    """An Objective-C property's value, whether Rubicon gave it or its getter."""
    return attribute() if callable(attribute) else attribute
