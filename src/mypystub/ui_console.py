"""Setup's Experimental Console: toga-console in the Script tab.

`toga-console <https://github.com/beeware/toga-console>`_ is BeeWare's console
widget: output on named streams (stderr in red), escape sequences handled, a
bounded scrollback, and typed input after the last output. With the Setup
switch on, the next run's Script tab shows one instead of the usual output and
error panes: the prototype's output and errors (in red) go into it, and it is
typeable for the whole run, feeding ``sys.stdin`` (see ``hooks.ConsoleStdin``),
so Python's own ``input()`` and any other reading of stdin work as at a
terminal, with no hook. Only ``getpass()`` is still hooked, to its password
field, since the console echoes what is typed. The keyboard covering the
console on a phone isn't handled yet.
"""

from __future__ import annotations

from typing import Any

SETTING = "experimental_console"  # launcher.toml flag, off by default


def make_console() -> Any | None:
    """A new console for the Script tab, or None if toga-console can't load."""
    try:
        from toga_console import Console  # pyright: ignore[reportMissingImports]
    except ImportError as error:
        print(f"Experimental Console unavailable: {error}")
        return None
    return Console(readonly=True, follow=True, flex=1)
