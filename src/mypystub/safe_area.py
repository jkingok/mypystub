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
:mod:`mypystub.android_insets`. Android doesn't resize the window for the
keyboard, so without this it covers whatever is at the bottom.

Elsewhere it is a plain Box: desktop platforms lay windows out inside their
safe area and move content for the keyboard themselves.
"""

from __future__ import annotations

import sys
from collections.abc import Callable, Iterable
from typing import Any, NamedTuple

import toga


class Insets(NamedTuple):
    """Space, in points, to keep clear on each side (whole points once worked out)."""

    top: float = 0
    right: float = 0
    bottom: float = 0
    left: float = 0


NO_INSETS = Insets()

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


class SafeArea(toga.Box):
    """A Box whose children stay where they can be seen and tapped.

    Use it instead of the Box that is a window's or a tab's content; it takes
    the same arguments, with `direction` and the rest of the style as usual.
    On iOS its children are moved in by the box's safe area (status and
    navigation bars, tab bars, the notch or Dynamic Island, the rounded
    corners and the home indicator, in whatever orientation) and, unless
    `keyboard` is False, by the part of the box the keyboard covers. A
    hardware keyboard's shortcut bar counts as keyboard too.

    The space is added to the children's own margins: along the direction
    only the first and last child get it (the top and bottom of a column, the
    left and right of a row); across it, every child does. It changes as the
    safe area and keyboard do, and follows children as they are added,
    removed or replaced. `on_change` is called with the box and the new
    :class:`Insets` each time.

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
        # Each child given extra margin, with the margin it had of its own
        self._own_margins: dict[toga.Widget, tuple[float, float, float, float]] = {}
        self._pending: tuple[Insets, bool] | None = None
        self._squeezed: list[toga.Widget] = []
        self._observer: Any = None  # the native object watching the box
        self._box_observer: Any = None  # iOS: a second one, for the box's size
        # Squeezed text views' own top and bottom padding, by id, to put back
        self._paddings: dict[int, tuple[float, float]] = {}
        # Positionally: the launcher never names widget ids (see test_ui_app_isolation)
        super().__init__(id, style, children, **kwargs)
        if sys.platform == "ios":
            self._observe()
        elif sys.platform == "android":
            self._observe_android()

    @property
    def insets(self) -> Insets:
        """The space the children are kept clear by now."""
        return self._insets

    # Every change of children (replace and clear included) comes through these

    def add(self, *children: toga.Widget) -> None:
        """Add children, as Box does, keeping the edges clear."""
        super().add(*children)
        self._place_insets()

    def insert(self, index: int, child: toga.Widget) -> None:
        """Insert a child, as Box does, keeping the edges clear."""
        super().insert(index, child)
        self._place_insets()

    def remove(self, *children: toga.Widget) -> None:
        """Remove children, as Box does; they get their own margins back."""
        super().remove(*children)
        self._place_insets()

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
        self._place_insets()
        if self.on_change is not None:
            self.on_change(self, insets)

    def _place_insets(self) -> None:
        """Set each child's margin to its own plus its share of the insets."""
        if not hasattr(self, "_own_margins"):
            return  # Box.__init__ adding the first children
        insets = self._insets
        children = list(self.children)
        row = self.style.direction == "row"
        for index, child in enumerate(children):
            first, last = index == 0, index == len(children) - 1
            if row:
                extra = (
                    insets.top,
                    insets.right if last else 0,
                    insets.bottom,
                    insets.left if first else 0,
                )
            else:
                extra = (
                    insets.top if first else 0,
                    insets.right,
                    insets.bottom if last else 0,
                    insets.left,
                )
            if child not in self._own_margins:
                if not any(extra):
                    continue
                style = child.style
                self._own_margins[child] = (
                    style.margin_top,
                    style.margin_right,
                    style.margin_bottom,
                    style.margin_left,
                )
            own = self._own_margins[child]
            child.style.margin = tuple(o + e for o, e in zip(own, extra, strict=True))
        for child in [c for c in self._own_margins if c not in children]:
            child.style.margin = self._own_margins.pop(child)

    def _squeeze(self, on: bool) -> None:
        """Let scrolling widgets shrink to nothing, or give them their minimum back."""
        if on == bool(self._squeezed):
            return
        if on:
            self._squeezed = [
                widget for child in self.children for widget in scrolling_widgets(child)
            ]
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
        from . import bridge

        observer_class: Any = getattr(bridge, "SafeAreaObserverView")  # noqa: B009

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
        safe = native.safeAreaInsets
        height = float(native.bounds.size.height)
        clear = float(self._observer.frame.size.height)
        insets = insets_for(
            Insets(safe.top, safe.right, safe.bottom, safe.left),
            height,
            clear,
            self.keyboard,
        )
        keyboard_up = self.keyboard and height > 0 and height - clear > safe.bottom + 1
        self._schedule(insets, keyboard_up)

    def _observe_android(self) -> None:
        """Have Android tell this box when its insets or position change."""
        from . import android_insets as native

        self._observer = native.watch(self._impl.native, self.android_changed)

    def android_changed(self, measure: AndroidMeasure, density: float) -> None:
        """Android reported new insets or a new position: pad again."""
        self._schedule(*android_padding(measure, density, self.keyboard))

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


def _value(attribute: Any) -> Any:
    """An Objective-C property's value, whether Rubicon gave it or its getter."""
    return attribute() if callable(attribute) else attribute
