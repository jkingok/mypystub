"""Short status text for activity rows, which are one line wide on a phone.

Labels don't wrap on iOS, so a long result runs off the edge of an iPhone SE.
Results are a few emoji and words instead, each emoji meaning one thing
wherever it is used; the detail is on the page and in the log. Free of Toga
imports so it can be unit tested on desktop.
"""

from __future__ import annotations

PACKAGES = "📦"  # packages: the user's, and updating them
APP = "📱"  # the app itself: its build, Python and bundled packages
CHECKING = "🔍"  # asking something (PyPI, a git host, python.org)
OK = "✅"  # fine, up to date, done
WARN = "⚠️"  # something to do or know
FAILED = "❌"  # couldn't do it
DELETED = "🗑️"  # removed
SEPARATOR = " · "


def packages_result(updates: int) -> str:
    """The user's packages after a check: ``📦 ✅ up to date``, ``📦 ⚠️ 3 to update``."""
    if updates:
        return f"{PACKAGES} {WARN} {updates} to update"
    return f"{PACKAGES} {OK} up to date"


def app_result(count: int, newer_build: bool = False) -> str:
    """The app after a check: ``📱 ✅ up to date``, ``📱 ⚠️ 4 behind``."""
    if newer_build:
        return f"{APP} {WARN} new build"
    if count:
        return f"{APP} {WARN} {count} behind"
    return f"{APP} {OK} up to date"


def could_not_check(what: str) -> str:
    """``📦 ❌ no answer``: the reason goes on the page and in the log."""
    return f"{what} {FAILED} no answer"


def join(*results: str) -> str:
    """The results that say anything, on one line."""
    return SEPARATOR.join(r for r in results if r)


def checking(name: str) -> str:
    """``🔍 rich``: what is being asked about now."""
    return f"{CHECKING} {name}"
