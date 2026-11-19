"""Android's on-screen keyboard: put it away.

When a focused text field is taken off the screen, iOS closes its keyboard,
but Android moves the focus to the next view that takes it (the tab bar) and
leaves the keyboard open over the layout. Closing it goes through Chaquopy's
``java`` module, which only exists on Android.
"""

from __future__ import annotations

from typing import Any


def hide(view: Any) -> None:
    """Close the keyboard `view` (an Android View) opened, and drop its focus.

    A view already taken off the screen has no window token, so the
    activity's window is asked instead, and whatever has the focus loses it.
    """
    from java import jclass  # type: ignore[import-not-found]  # Chaquopy

    context = jclass("android.content.Context")
    activity = jclass("org.beeware.android.MainActivity").singletonThis
    manager = activity.getSystemService(context.INPUT_METHOD_SERVICE)
    token = (
        view.getWindowToken() or activity.getWindow().getDecorView().getWindowToken()
    )
    if manager is not None and token is not None:
        manager.hideSoftInputFromWindow(token, 0)
    view.clearFocus()
    focused = activity.getCurrentFocus()
    if focused is not None:
        focused.clearFocus()
