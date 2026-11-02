"""What the launcher list's swipe actions do for each kind of row.

Toga's swipe actions belong to the whole list, so every row offers both "Info"
and Setup. Rows that have nothing to show or run explain why, in words
that fit the row, instead of a generic error.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

RowType = Literal["category", "up", "folder", "script", "project", "other"]

# Checked in this order; the first that exists (in any letter case) is shown
README_NAMES = ("readme.md", "readme.markdown", "readme.txt", "readme")

CATEGORY_PURPOSE = {
    "Examples": "Examples holds the bundled examples.",
    "Documents": "Documents holds your own scripts and projects.",
}


def row_type(row: Any) -> RowType:
    """Classify a launcher list row by the keys the launcher gave it."""
    if getattr(row, "categories", False) or getattr(row, "title", None) == "..":
        return "up"
    if getattr(row, "category", None):
        return "category"
    kind = getattr(row, "kind", None)
    if kind in ("folder", "script", "project"):
        return kind
    return "other"


def runnable(kind: RowType) -> bool:
    """Whether rows of this type run when tapped, and so have run settings."""
    return kind in ("script", "project")


def find_readme(folder: Path) -> Path | None:
    """The folder's README file, if it has one."""
    try:
        files = {p.name.lower(): p for p in folder.iterdir() if p.is_file()}
    except OSError:
        return None
    for name in README_NAMES:
        if name in files:
            return files[name]
    return None


def run_with_message(kind: RowType, title: str, where: str = "") -> str:
    """Why Setup has nothing to set on a row that can't run.

    `where` is where a ".." row leads, such as "Examples/basics".
    """
    match kind:
        case "category":
            purpose = CATEGORY_PURPOSE.get(title, f"{title} is a category.")
            return (
                f"{purpose} There's nothing to run here. Open it and swipe a "
                "script or project to choose how it runs."
            )
        case "folder":
            return (
                f"{title} is a folder, so there's nothing to run. Open it and "
                "swipe a script or project inside."
            )
        case "up":
            return f"This row goes back to {where}, so there's nothing to run."
        case _:
            return f"{title} can't be run, so there's nothing to set."


def no_readme_message(kind: RowType, title: str, summary: str) -> str:
    """What Info says about a category or folder that has no README.

    `summary` describes the folder's contents, as folder rows show it.
    """
    purpose = CATEGORY_PURPOSE.get(title, "") if kind == "category" else ""
    if summary == "Empty folder":
        contents = f"{title} is empty."
    else:
        contents = f"It holds {summary[0].lower()}{summary[1:]}."
    lead = f"{purpose} " if purpose else ""
    return f"{lead}{title} has no README to show. {contents} Add a README.md to describe it."


def up_info_message(where: str) -> str:
    """What Info says about a ".." row."""
    return f"This row goes back to {where}, so there's nothing to describe."


def prototype_summary(row: Any) -> str:
    """A short description of a script or project, until the full Info view."""
    lines = [str(getattr(row, "subtitle", "") or "")]
    dependencies = list(getattr(row, "dependencies", None) or [])
    if dependencies:
        lines.append("Dependencies: " + ", ".join(dependencies))
    else:
        lines.append("No dependencies.")
    return "\n\n".join(line for line in lines if line)
