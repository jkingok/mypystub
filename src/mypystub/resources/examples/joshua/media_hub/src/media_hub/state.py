"""This app's shared state, in one place.

It lives here, in a plain object of our own, rather than as attributes on the
toga.App. The app object is Toga's (and, when this runs inside another host,
shared with it), so anything attached to it can clash with something else
using the same name.
"""

from typing import Any


class State:
    """What the parts of the app share."""

    def __init__(self) -> None:
        """Start empty; the prototype fills these in."""
        self.proto: Any = None
        self.settings: Any = None
        self.functions: Any = None
        self.model: Any = None


state = State()
