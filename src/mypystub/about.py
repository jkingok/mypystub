"""Collects details about the running Python environment for the About view.

Kept free of Toga imports so it can be unit tested on desktop.
"""

import platform
import sys
from collections.abc import Mapping
from html import escape
from pathlib import Path

from .piplike import ALIASES, Alias, get_package_inventory

Row = tuple[str, str]
Section = tuple[str, list[Row]]


def python_rows() -> list[Row]:
    """Describe the interpreter and platform the app is running on."""
    return [
        ("Version", platform.python_version()),
        ("Implementation", platform.python_implementation()),
        ("Build", " ".join(platform.python_build())),
        ("Compiler", platform.python_compiler()),
        ("Executable", sys.executable or "(embedded)"),
        ("sys.platform", sys.platform),
        ("Platform", platform.platform()),
        ("Machine", platform.machine()),
    ]


def package_sections(user_site: Path) -> list[Section]:
    """List bundled and user-installed distributions as two sections.

    The user site is added to ``sys.path`` once a prototype with dependencies has
    run, so anything found there is reported as user-installed, not bundled.
    """
    user = get_package_inventory(user_site)
    bundled = {
        name: version
        for name, version in get_package_inventory(None).items()
        if name not in user
    }
    return [
        (f"Bundled packages ({len(bundled)})", sorted(bundled.items())),
        (f"User packages ({len(user)})", sorted(user.items())),
    ]


def alias_rows(aliases: Mapping[str, Alias]) -> list[Row]:
    """Describe package aliases (#79), sorted by requirement name."""
    rows: list[Row] = []
    for name, alias in sorted(aliases.items()):
        if alias.kind == "bundled":
            how = "bundled with the app"
        elif alias.when == "always":
            how = "always"
        else:
            how = "when no compatible wheel"
        rows.append((name, f"{alias.target} ({how})"))
    return rows


def collect_environment(
    app_name: str,
    app_version: str | None,
    paths: Mapping[str, Path],
    user_site: Path,
    aliases: Mapping[str, Alias] | None = None,
) -> list[Section]:
    """Gather every section shown on the About page."""
    return [
        ("App", [("Name", app_name), ("Version", app_version or "unknown")]),
        ("Python", python_rows()),
        ("Paths", [(name, str(path)) for name, path in paths.items()]),
        *package_sections(user_site),
        ("Package aliases", alias_rows({**ALIASES, **(aliases or {})})),
    ]


def to_text(sections: list[Section]) -> str:
    """Render sections as plain text, for sharing in bug reports."""
    lines: list[str] = []
    for title, rows in sections:
        lines.append(f"## {title}")
        lines += [f"{key}: {value}" for key, value in rows] or ["(none)"]
        lines.append("")
    return "\n".join(lines)


def to_html(sections: list[Section]) -> str:
    """Render sections as HTML tables for the About web view."""
    parts: list[str] = []
    for title, rows in sections:
        parts.append(f"<h2>{escape(title)}</h2>")
        if not rows:
            parts.append("<p>(none)</p>")
            continue
        parts.append("<table>")
        parts += [
            f"<tr><th>{escape(key)}</th><td>{escape(value)}</td></tr>"
            for key, value in rows
        ]
        parts.append("</table>")
    return "\n".join(parts)
