"""HTML bodies for the Setup tab's detail pages.

Toga Labels don't wrap, so each Setup section opens a page that shows its
details in a WebView (wrapped through ``pages.html_page``) with native buttons
for its actions underneath. Kept free of Toga imports so it can be tested on
desktop.
"""

from collections.abc import Mapping, Sequence
from html import escape

from .maintenance import Health, Update

NOT_CHECKED = "Not checked yet."


def table(rows: Sequence[tuple[str, str]], headings: tuple[str, str]) -> str:
    """A two-column table with escaped cells."""
    head = f"<tr><th>{escape(headings[0])}</th><th>{escape(headings[1])}</th></tr>"
    body = "".join(
        f"<tr><td>{escape(left)}</td><td>{escape(right)}</td></tr>"
        for left, right in rows
    )
    return f"<table>{head}{body}</table>"


def packages_html(
    summary: str,
    inventory: Mapping[str, str],
    updates: Sequence[Update] | None,
    update_error: str | None = None,
) -> str:
    """The Packages page: what's installed, and any updates found.

    :param summary: e.g. "6 user packages (6.4 MB)".
    :param inventory: Installed user packages, name to version.
    :param updates: Updates from the last check, or None if not checked yet.
    :param update_error: Why the last check failed, if it did.
    """
    parts = [f"<h2>Packages</h2><p>{escape(summary)}</p>"]
    if inventory:
        rows = [(name, version) for name, version in sorted(inventory.items())]
        parts.append(table(rows, ("Package", "Version")))
    parts.append("<h3>Updates</h3>")
    if update_error is not None:
        parts.append(f"<p>Couldn't check: {escape(update_error)}</p>")
    elif updates is None:
        parts.append(f"<p>{NOT_CHECKED} <b>Check for updates</b> asks PyPI.</p>")
    elif not updates:
        parts.append("<p>✓ Up to date</p>")
    else:
        rows = [(u.name, f"{u.installed} → {u.latest}") for u in updates]
        parts.append(table(rows, ("Package", "Update")))
        parts.append("<p><b>Update all</b> installs these versions.</p>")
    parts.append(
        "<p><b>Wipe user packages</b> deletes everything installed here. "
        "Prototypes reinstall their dependencies on their next run, which needs "
        "the network.</p>"
    )
    return "".join(parts)


def health_html(health: Health | None, error: str | None = None) -> str:
    """The App health page: things only a new app build can update."""
    parts = ["<h2>App health</h2>"]
    if error is not None:
        parts.append(f"<p>Couldn't check (offline?)</p><p>{escape(error)}</p>")
    elif health is None:
        parts.append(
            f"<p>{NOT_CHECKED} <b>Check app health</b> compares this app's Python "
            "and bundled packages with python.org and PyPI.</p>"
        )
    else:
        parts.append(f"<p>{escape(health.summary)}</p>")
        details = health.details()
        if details:
            items = "".join(f"<li>{escape(line)}</li>" for line in details)
            parts.append(f"<ul>{items}</ul>")
    parts.append(
        "<p>These can only be updated by a new app build (TestFlight), so there's "
        "nothing to do here except check.</p>"
    )
    return "".join(parts)


def permissions_html(statuses: Mapping[str, str]) -> str:
    """The Permissions page: each declared permission's status."""
    return (
        "<h2>Permissions</h2>"
        + table(list(statuses.items()), ("Permission", "Status"))
        + "<p>Changed your mind? A permission appears in the Settings app once a "
        "prototype has asked for it. <b>Open Settings</b> goes to this app's page "
        "there.</p>"
        "<p>iOS has no way to ask about local network access, so it always shows "
        "as Unknown.</p>"
    )
