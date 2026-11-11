"""HTML bodies for the Setup tab's detail pages.

Toga Labels don't wrap, so each Setup section opens a page that shows its
details in a WebView (wrapped through ``pages.html_page``) with native buttons
for its actions underneath. Kept free of Toga imports so it can be tested on
desktop.
"""

from collections.abc import Mapping, Sequence
from html import escape

from .maintenance import Health, Update
from .pages import readme_html

NOT_CHECKED = "Not checked yet."


def table(rows: Sequence[tuple[str, str]], headings: tuple[str, str]) -> str:
    """A two-column table with escaped cells."""
    head = f"<tr><th>{escape(headings[0])}</th><th>{escape(headings[1])}</th></tr>"
    body = "".join(
        f"<tr><td>{escape(left)}</td><td>{escape(right)}</td></tr>"
        for left, right in rows
    )
    return f"<table>{head}{body}</table>"


def details(summary: str, body: str) -> str:
    """A collapsible section, closed until the reader opens it."""
    return f"<details><summary>{escape(summary)}</summary>{body}</details>"


def build_notes(health: Health) -> str:
    """For a newer build: a link to its Release and a fold with its What's New."""
    build = health.build
    if build is None or not build.newer:
        return ""
    parts = []
    if build.url.startswith("https://"):
        parts.append(
            f'<p><a href="{escape(build.url)}">What\'s new in {escape(build.latest)}</a></p>'
        )
    if build.notes:
        parts.append(
            # A Release's body is Markdown (#208). It comes from GitHub, so it is
            # rendered as an untrusted README: raw HTML as text, safe links only
            "<details><summary>What's new</summary>"
            f"{readme_html(build.notes, 'notes.md')}</details>"
        )
    return "".join(parts)


def health_section(
    health: Health | None,
    error: str | None = None,
    build_error: str | None = None,
) -> str:
    """App health: things only a new app build can update.

    `build_error` is why the check for a newer build failed, if it did; the
    other checks can still have a result.
    """
    parts = ["<h3>App health</h3>"]
    if build_error is not None:
        parts.append(
            "<p>Couldn't check for a newer build "
            f"(offline? rate-limited?): {escape(build_error)}</p>"
        )
    if error is not None:
        parts.append(f"<p>Couldn't check (offline?)</p><p>{escape(error)}</p>")
    elif health is None:
        parts.append(
            f"<p>{NOT_CHECKED} <b>Check for updates</b> also compares this app's "
            "Python and bundled packages with python.org and PyPI.</p>"
        )
    else:
        parts.append(f"<p>{escape(health.summary)}</p>")
        found = health.details()
        if found:
            items = "".join(f"<li>{escape(line)}</li>" for line in found)
            parts.append(f"<ul>{items}</ul>")
        parts.append(build_notes(health))
    parts.append(
        "<p>The app's own Python and bundled packages can only be updated by a "
        "new app build (TestFlight), so there's nothing to do about them here "
        "except check.</p>"
    )
    return "".join(parts)


def packages_html(
    summary: str,
    inventory: Mapping[str, str],
    updates: Sequence[Update] | None,
    update_error: str | None = None,
    *,
    python: Sequence[tuple[str, str]] = (),
    bundled: Mapping[str, str] | None = None,
    aliases: Sequence[tuple[str, str]] = (),
    health: Health | None = None,
    health_error: str | None = None,
    build_error: str | None = None,
) -> str:
    """The Packages page: everything about the Python and packages in this app.

    :param summary: e.g. "6 user packages (6.4 MB)".
    :param inventory: Installed user packages, name to version.
    :param updates: Updates from the last check, or None if not checked yet.
    :param update_error: Why the last check failed, if it did.
    :param python: Rows describing the interpreter (version, implementation...).
    :param bundled: Packages bundled with the app, name to version, if shown.
    :param aliases: Package aliases in effect, as (name, how) rows.
    :param health: The app health result from the last check, if any.
    :param health_error: Why the last health check failed, if it did.
    :param build_error: Why checking for a newer build failed, if it did.
    """
    parts = ["<h2>Packages</h2>"]
    if python:
        parts.append("<h3>Python</h3>" + table(list(python), ("", "")))
    if bundled is not None:
        rows = sorted(bundled.items())
        parts.append(
            "<h3>Bundled with the app</h3>"
            + details(f"{len(rows)} packages", table(rows, ("Package", "Version")))
        )
    parts.append(f"<h3>User packages</h3><p>{escape(summary)}</p>")
    if inventory:
        rows = [(name, version) for name, version in sorted(inventory.items())]
        parts.append(table(rows, ("Package", "Version")))
    parts.append("<h3>Updates</h3>")
    if update_error is not None:
        parts.append(f"<p>Couldn't check: {escape(update_error)}</p>")
    elif updates is None:
        parts.append(
            f"<p>{NOT_CHECKED} <b>Check for updates</b> asks PyPI about your "
            "user packages, and python.org and PyPI about the app.</p>"
        )
    elif not updates:
        parts.append("<p>✓ Up to date</p>")
    else:
        rows = [(u.name, f"{u.installed} → {u.latest}") for u in updates]
        parts.append(table(rows, ("Package", "Update")))
        parts.append("<p><b>Update all</b> installs these versions.</p>")
    parts.append(health_section(health, health_error, build_error))
    if aliases:
        parts.append(
            "<h3>Aliases</h3>"
            + details(f"{len(aliases)} aliases", table(list(aliases), ("Name", "Used")))
        )
    parts.append(
        "<p><b>Wipe user packages</b> deletes everything installed here. "
        "Prototypes reinstall their dependencies on their next run, which needs "
        "the network.</p>"
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
        + (
            "<p>iOS has no way to ask about local network access, so it always shows "
            "as Unknown.</p>"
            if "Local network" in statuses
            else ""
        )
    )
