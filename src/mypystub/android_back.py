"""Android's Back gesture and button, sent to a Python handler (Android only).

Neither Toga nor Briefcase's MainActivity passes Back to Python, so this adds an
AndroidX ``OnBackPressedCallback`` to the activity's ``OnBackPressedDispatcher``.
AndroidX delivers Back on every Android version, including Android 13 and later,
where Back is predictive and ``onBackPressed`` is no longer called.

``OnBackPressedCallback`` is an abstract class whose only constructor takes a
boolean, which Chaquopy's static proxy (it generates a constructor with no
arguments) can't extend. So ``PyBackCallback``, a small Java subclass beside the
app's other Java sources, extends it, and this module gives it a ``Handler``
through a dynamic proxy. When the handler declines (returns False), Android does
what it would have done anyway, usually leaving the app. This module imports
Java at its top: it is only ever imported on Android, from :func:`install`'s
caller.

MyPyStub's project template uses this same file (see new_items).
"""

from collections.abc import Callable
from typing import Any

from java import (  # pyright: ignore[reportMissingImports]
    dynamic_proxy,
    jclass,
)

PyBackCallback = jclass("au.id.jking.mypystub.PyBackCallback")


class BackHandler(dynamic_proxy(PyBackCallback.Handler)):  # type: ignore[misc]
    """Calls a Python handler for Back; if it declines, Android's default runs."""

    def __init__(self, handler: Callable[[], bool]) -> None:
        """Answer Back with `handler`."""
        super().__init__()
        self.handler = handler
        self.callback: Any = None  # the PyBackCallback this answers for

    def handle(self) -> None:
        """Back was pressed: the handler, or the system's default."""
        try:
            handled = bool(self.handler())
        except Exception as error:  # noqa: BLE001  (never leave Back dead)
            print(f"Back handler failed: {error}")
            handled = False
        if not handled:
            # The documented way to fall through: step aside and dispatch again
            self.callback.setEnabled(False)
            activity().getOnBackPressedDispatcher().onBackPressed()
            self.callback.setEnabled(True)


def activity() -> Any:
    """Briefcase's MainActivity, which keeps itself in a static field."""
    return jclass("org.beeware.android.MainActivity").singletonThis


_installed: list[BackHandler] = []  # kept alive while the app runs


def install(handler: Callable[[], bool]) -> None:
    """Send Back to `handler` from now on; installing again replaces it."""
    if _installed:
        _installed[0].handler = handler
        return
    proxy = BackHandler(handler)
    proxy.callback = PyBackCallback(proxy)
    main = activity()
    main.getOnBackPressedDispatcher().addCallback(main, proxy.callback)
    _installed.append(proxy)
