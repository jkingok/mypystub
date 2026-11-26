"""Safe area probe: what iOS reports about the screen, live, drawn on it.

Rotate, raise the keyboard (tap the field) and watch. Every half second it
reads, straight from UIKit:

- the interface orientation and the screen, window and Toga sizes;
- the window's safe-area insets, drawn as a **green** frame;
- this screen's own view and its safe-area insets, drawn **orange**;
- the safe area of a second, invisible window made with
  ``initWithWindowScene:`` (Toga makes its window another way), to compare;
- the status bar's frame (where the clock is), drawn **blue**;
- the keyboard's area, from this screen's keyboard layout guide, drawn **red**
  (along the bottom edge, or the safe bottom, when there's no keyboard).

A line is printed (and logged) each time something changes, so a rotation
leaves a record. Green should sit inside the notch, the rounded corners and
the home indicator in every orientation; if it doesn't, iOS (or the
Simulator) is reporting it wrong, whatever an app does with it.

On Android it reads the window's insets instead (status and navigation bars,
display cutout, keyboard), as text; elsewhere it shows what Toga reports.

It uses only Toga, toga_iOS.libs, Rubicon and Chaquopy's java, so it runs as
an app of its own too.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

import toga

TITLE = "Safe area probe"
APP_ID = "org.example.safeareaprobe"
ORIENTATIONS = {0: "unknown", 1: "portrait", 2: "upside down", 3: "landscape right",
                4: "landscape left"}  # fmt: skip


def edges(insets: Any) -> str:
    """Top, left, bottom, right, in points."""
    return f"t{insets.top:g} l{insets.left:g} b{insets.bottom:g} r{insets.right:g}"


def rect(r: Any) -> str:
    """x, y, width × height, in points."""
    return f"({r.origin.x:g}, {r.origin.y:g}) {r.size.width:g}×{r.size.height:g}"


class Probe:
    """The readings, and the coloured frames that show them on screen."""

    def __init__(self, app: toga.App, window: Any, content: toga.Widget) -> None:
        """Read `window` (None: the app's main window), showing `content`."""
        self.app = app
        self._window = window
        self.content = content
        self.text = toga.MultilineTextInput(readonly=True, flex=1, font_size=11)
        self.frames: dict[str, Any] = {}
        self.scene_window: Any = None  # see scene_safe
        self.last = ""
        self.running = True

    @property
    def window(self) -> Any:
        """The window being read (standalone, Toga makes it after startup)."""
        return self._window or self.app.main_window

    def frame(self, name: str, colour: str) -> Any:
        """A see-through view with a coloured border, laid over the window."""
        from toga_iOS.libs import UIColor, UIView  # pyright: ignore[reportMissingImports]

        if name not in self.frames:
            view = UIView.alloc().init()
            view.userInteractionEnabled = False
            view.backgroundColor = UIColor.clearColor
            view.layer.borderWidth = 2
            view.layer.borderColor = getattr(UIColor, f"{colour}Color").CGColor
            window = self.window._impl.native
            window.addSubview(view)
            if name == "keyboard":
                # Pinned to a keyboard layout guide, which UIKit only lays
                # out once something is constrained to it: the top of this
                # view is the top of the keyboard (the window's bottom without)
                view.translatesAutoresizingMaskIntoConstraints = False
                for constraint in (
                    view.leadingAnchor.constraintEqualToAnchor(window.leadingAnchor),
                    view.trailingAnchor.constraintEqualToAnchor(window.trailingAnchor),
                    # This screen's guide: the window's own doesn't follow
                    # the keyboard (seen on iOS 27.2), a view's does
                    view.topAnchor.constraintEqualToAnchor(
                        self.content._impl.native.keyboardLayoutGuide.topAnchor
                    ),
                    view.bottomAnchor.constraintEqualToAnchor(window.bottomAnchor),
                ):
                    constraint.setActive(True)
            self.frames[name] = view
        return self.frames[name]

    def scene_safe(self, scene: Any) -> Any:
        """The safe area of a window made the current way, for comparison.

        Toga makes its window with ``initWithFrame:`` and attaches it to the
        scene afterwards. This one is made with ``initWithWindowScene:``, as
        Apple's templates do, and kept invisible behind everything. If its
        insets turn with the device while Toga's window's don't, the way the
        window is made is why.
        """
        from toga_iOS.libs import (  # pyright: ignore[reportMissingImports]
            UIColor,
            UIViewController,
            UIWindow,
        )

        if self.scene_window is None:
            window = UIWindow.alloc().initWithWindowScene(scene)
            window.rootViewController = UIViewController.alloc().init()
            window.backgroundColor = UIColor.clearColor
            window.userInteractionEnabled = False
            window.windowLevel = -1000.0
            window.alpha = 0.01
            window.hidden = False
            self.scene_window = window
        return self.scene_window.safeAreaInsets

    def read(self) -> str:
        """Read everything once, and move the frames to match."""
        from rubicon.objc import CGRect  # pyright: ignore[reportMissingImports]
        from toga_iOS.libs import UIScreen  # pyright: ignore[reportMissingImports]

        native = self.window._impl.native
        scene = native.windowScene
        bounds = native.bounds
        safe = native.safeAreaInsets
        scene_safe = self.scene_safe(scene)
        view = self.content._impl.native
        view_frame = view.convertRect(view.bounds, toView=None)
        view_safe = view.safeAreaInsets
        status = scene.statusBarManager.statusBarFrame
        keyboard = self.frame("keyboard", "red").frame  # placed by UIKit
        w, h = bounds.size.width, bounds.size.height
        self.frame("safe", "green").frame = CGRect(
            (safe.left, safe.top),
            (w - safe.left - safe.right, h - safe.top - safe.bottom),
        )
        self.frame("view", "orange").frame = CGRect(
            (view_frame.origin.x + view_safe.left, view_frame.origin.y + view_safe.top),
            (
                view_frame.size.width - view_safe.left - view_safe.right,
                view_frame.size.height - view_safe.top - view_safe.bottom,
            ),
        )
        self.frame("status", "blue").frame = status
        screen = UIScreen.mainScreen
        return "\n".join(
            [
                f"orientation: {ORIENTATIONS.get(scene.interfaceOrientation, '?')}",
                f"screen: {rect(screen.bounds)} at {screen.scale:g}x",
                f"window: {rect(native.frame)}; Toga: {self.window.size}",
                f"window safe (green): {edges(safe)}",
                f"scene window safe: {edges(scene_safe)}",
                f"view: {rect(view_frame)}",
                f"view safe (orange): {edges(view_safe)}",
                f"status bar (blue): {rect(status)}"
                + (" hidden" if scene.statusBarManager.statusBarHidden else ""),
                f"keyboard top (red): {keyboard.origin.y:g} of {h:g}"
                + ("" if keyboard.size.height > 0 else " (no keyboard)"),
            ]
        )

    async def watch(self) -> None:
        """Read twice a second until Back; print each change."""
        while self.running:
            try:
                text = self.read()
            except Exception as error:  # noqa: BLE001  (show it, keep watching)
                text = f"Couldn't read: {error!r}"
            if text != self.last:
                self.last = text
                self.text.value = text
                print(f"--- {TITLE}\n{text}")
            await asyncio.sleep(0.5)

    def stop(self) -> None:
        """Stop watching and take the frames away."""
        self.running = False
        for view in self.frames.values():
            view.removeFromSuperview()
        self.frames.clear()
        if self.scene_window is not None:
            self.scene_window.hidden = True
            self.scene_window = None


class AndroidProbe:
    """The same readings on Android, from the window's insets (in dp).

    Android reports, to the content's view, how much of the window the status
    and navigation bars, the display cutout and the keyboard (IME) take. No
    frames are drawn: the readings are text only.
    """

    def __init__(self, app: toga.App, content: toga.Widget) -> None:
        """Read the view of `content` (this screen)."""
        self.app = app
        self.content = content
        self.text = toga.MultilineTextInput(readonly=True, flex=1, font_size=11)
        self.last = ""
        self.running = True

    def read(self) -> str:
        """Read everything once."""
        from java import jarray, jclass, jint  # pyright: ignore[reportMissingImports]

        view = self.content._impl.native
        density = float(view.getResources().getDisplayMetrics().density)
        root = view.getRootWindowInsets()
        if root is None:
            return "no insets yet (the view isn't attached)"
        sdk = int(jclass("android.os.Build$VERSION").SDK_INT)
        location = jarray(jint)([0, 0])
        view.getLocationInWindow(location)
        width, height = view.getWidth() / density, view.getHeight() / density
        lines = [
            f"Android API {sdk}, density {density:g}",
            (
                f"view: ({location[0] / density:g}, {location[1] / density:g}) "
                f"{width:g}×{height:g} dp"
            ),
        ]
        if sdk >= 30:  # WindowInsets.Type
            kinds = jclass("android.view.WindowInsets$Type")
            for name, kind in (
                ("status bars", kinds.statusBars()),
                ("navigation bars", kinds.navigationBars()),
                ("display cutout", kinds.displayCutout()),
                ("keyboard (IME)", kinds.ime()),
            ):
                inset = root.getInsets(kind)
                lines.append(f"{name}: {android_edges(inset, density)}")
        else:
            lines.append(
                "system window: "
                f"t{root.getSystemWindowInsetTop() / density:g} "
                f"l{root.getSystemWindowInsetLeft() / density:g} "
                f"b{root.getSystemWindowInsetBottom() / density:g} "
                f"r{root.getSystemWindowInsetRight() / density:g}"
            )
        cutout = root.getDisplayCutout()
        if cutout is not None:
            rects = [
                f"({r.left / density:g}, {r.top / density:g})"
                f" {r.width() / density:g}×{r.height() / density:g}"
                for r in cutout.getBoundingRects()
            ]
            lines.append("cutout shapes: " + ", ".join(rects))
        window: Any = self.app.main_window
        lines.append(f"Toga window: {window.size}")
        return "\n".join(lines)

    watch = Probe.watch
    stop = Probe.stop

    @property
    def frames(self) -> dict[str, Any]:
        """None drawn on Android."""
        return {}

    scene_window = None


class DesktopProbe(AndroidProbe):
    """Off iOS and Android: what Toga itself reports, as a fallback."""

    def read(self) -> str:
        """Toga's window and screen sizes; there's no safe area to read."""
        window: Any = self.app.main_window
        screens = [f"{s.name}: {s.size}" for s in self.app.screens]
        return "\n".join(
            [
                f"platform: {sys.platform}",
                f"window: {window.size} at {window.position}",
                "screens: " + "; ".join(screens),
                "no safe area or keyboard to report on this platform",
            ]
        )


def android_edges(inset: Any, density: float) -> str:
    """An android.graphics.Insets as top, left, bottom, right, in dp."""
    return (
        f"t{inset.top / density:g} l{inset.left / density:g} "
        f"b{inset.bottom / density:g} r{inset.right / density:g}"
    )


def build(app: toga.App, window: Any, back: Any = None) -> toga.Widget:
    """This screen; `back` (inside MyPyStub) puts the launcher back."""
    field = toga.TextInput(placeholder="Tap here to raise the keyboard", flex=1)
    top = toga.Row(children=[field])
    content = toga.Column(flex=1, children=[top])
    probe: Any
    if sys.platform == "ios":
        probe = Probe(app, window, content)
    elif sys.platform == "android":
        probe = AndroidProbe(app, content)
    else:
        probe = DesktopProbe(app, content)
    content.add(probe.text)
    if back:

        def leave(widget: toga.Widget) -> None:
            probe.stop()
            back(widget)

        top.insert(0, toga.Button("Back", on_press=leave))
    app.loop.call_soon(lambda: asyncio.ensure_future(probe.watch()))
    return content


def startup(app: toga.App, **kwargs: Any) -> toga.Widget:
    """The probe as an app of its own."""
    return build(app, None)


# Standalone it is its own app. Inside MyPyStub (a running app whose main
# window keeps a content_stack, plain Toga) it takes over the screen instead,
# with Back to hand it back.


def launcher_window() -> Any:
    """MyPyStub's main window, when this runs inside it; otherwise None."""
    app = toga.App.app
    window = getattr(app, "main_window", None) if app is not None else None
    return window if hasattr(window, "content_stack") else None


def take_over(app: toga.App, window: Any) -> None:
    """Show the probe over the launcher. Runs on the app's main thread."""
    stack = window.content_stack
    stack.append((window.title, window.content))

    def back(widget: toga.Widget | None) -> None:
        window.title, window.content = stack.pop()

    window.title = TITLE
    window.content = build(app, window, back)


def main() -> None:
    """Run the probe as an app of its own, or over MyPyStub's screen."""
    window = launcher_window()
    if window is not None:
        app = toga.App.app
        assert app is not None
        # Scripts run on a background thread; the screen changes on the main one
        app.loop.call_soon_threadsafe(take_over, app, window)
        print(f"{TITLE}: shown over the launcher; Back returns.")
        return
    toga.App(TITLE, APP_ID, startup=startup).main_loop()


if __name__ == "__main__":
    main()
