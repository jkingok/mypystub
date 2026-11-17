"""Android's Back gesture and button, routed to the launcher (BackMixin).

Neither Toga nor Briefcase's MainActivity passes Back to Python, so this adds an
AndroidX ``OnBackPressedCallback`` to the activity's ``OnBackPressedDispatcher``.
AndroidX delivers Back on every Android version, including Android 13 and later,
where Back is predictive and ``onBackPressed`` is no longer called.

``OnBackPressedCallback`` is an abstract class, not an interface, so Chaquopy
can only extend it with a static proxy, which is compiled into the app at build
time: pyproject.toml names this module in ``chaquopy.defaultConfig.staticProxy``.
That is why this module imports Java at its top: it is only ever imported on
Android, from :func:`install`'s caller.
"""

from collections.abc import Callable
from typing import Any

from androidx.activity import (  # pyright: ignore[reportMissingImports]
    OnBackPressedCallback,
)
from java import (  # pyright: ignore[reportMissingImports]
    Override,
    constructor,
    jboolean,
    jclass,
    jvoid,
    static_proxy,
)


class BackCallback(static_proxy(OnBackPressedCallback)):  # type: ignore[misc]
    """Calls a Python handler for Back; if it declines, Android's default runs."""

    @constructor([jboolean])
    def __init__(self, enabled: bool) -> None:
        """Enabled from the start: the handler decides each time."""
        super().__init__(enabled)
        self.handler: Callable[[], bool] = lambda: False

    @Override(jvoid, [])
    def handleOnBackPressed(self) -> None:
        """Back was pressed: the handler, or the system's default."""
        try:
            handled = bool(self.handler())
        except Exception as error:  # noqa: BLE001  (never leave Back dead)
            print(f"Back handler failed: {error}")
            handled = False
        if not handled:
            # The documented way to fall through: step aside and dispatch again
            self.setEnabled(False)
            activity().getOnBackPressedDispatcher().onBackPressed()
            self.setEnabled(True)


def activity() -> Any:
    """Briefcase's MainActivity, which keeps itself in a static field."""
    return jclass("org.beeware.android.MainActivity").singletonThis


_installed: list[BackCallback] = []  # kept alive while the app runs


def install(handler: Callable[[], bool]) -> None:
    """Send Back to `handler` from now on; installing again replaces it."""
    if _installed:
        _installed[0].handler = handler
        return
    callback = BackCallback(True)
    callback.handler = handler
    main = activity()
    main.getOnBackPressedDispatcher().addCallback(main, callback)
    _installed.append(callback)
