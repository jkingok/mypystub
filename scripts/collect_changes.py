"""Collect change fragments into "What's New" at release time (#126).

Each pull request with a user-facing change adds a small file,
``changes/<number>.<type>.md``, holding one or two plain sentences. Types are
``feature`` (shown as New), ``bugfix`` (shown as Fixed) and ``misc`` (not
shown). A file per change means branches never edit the same lines.

Fastlane runs this when a build is made, once it knows the version:

- the fragments become a section, ``## <version> (<date>)``, at the top of
  ``src/mypystub/resources/templates/changes.md``, which the app shows;
- a second build on the same day adds to that day's section;
- sections more than 30 days old move to ``changes-archive.md``, which the
  app doesn't show, but the newest three sections always stay;
- the collected fragments are deleted.

Usage::

    uv run scripts/collect_changes.py 2026.11.3.1
    uv run scripts/collect_changes.py --notes 2026.11.3.1

The second form prints that build's section as plain text, for TestFlight's
"What to Test". It prints nothing if the build has no section.
"""

import argparse
import re
from datetime import date, timedelta
from pathlib import Path

TITLE = "# What's New"
SHOWN_AS = {"feature": "New", "bugfix": "Fixed"}  # misc isn't shown
FRAGMENT = re.compile(r"^(?P<number>[\w-]+)\.(?P<kind>feature|bugfix|misc)\.md$")
VERSION = re.compile(r"\d{4}\.[1-9]\d?\.[1-9]\d?\.[1-9]\d*")
HEADING = re.compile(r"^## (?P<version>\S+) \((?P<date>\d{4}-\d{2}-\d{2})\)$")
KEEP_DAYS = 30
MIN_SECTIONS = 3
WHATS_NEW = Path("src/mypystub/resources/templates/changes.md")
ARCHIVE = Path("changes-archive.md")


class Section:
    """One release's entry: a version, a date and bullets under New/Fixed."""

    def __init__(self, version: str, day: date) -> None:
        """Start an empty section."""
        self.version = version
        self.day = day
        self.groups: dict[str, list[str]] = {title: [] for title in SHOWN_AS.values()}

    def render(self) -> str:
        """The section as Markdown, with only the groups that have bullets."""
        lines = [f"## {self.version} ({self.day.isoformat()})", ""]
        for title, bullets in self.groups.items():
            if bullets:
                lines += [f"### {title}", ""]
                lines += [f"- {bullet}" for bullet in bullets]
                lines.append("")
        return "\n".join(lines).rstrip("\n") + "\n"


def parse(text: str) -> list[Section]:
    """Read sections (newest first, as written) from a What's New file."""
    sections: list[Section] = []
    group = ""
    for line in text.splitlines():
        if match := HEADING.match(line):
            sections.append(
                Section(match["version"], date.fromisoformat(match["date"]))
            )
            group = ""
        elif line.startswith("### ") and sections:
            group = line[4:].strip()
        elif line.startswith("- ") and sections and group in sections[-1].groups:
            sections[-1].groups[group].append(line[2:].strip())
    return sections


def render(sections: list[Section]) -> str:
    """A What's New (or archive) file for `sections`."""
    return TITLE + "\n\n" + "\n".join(section.render() for section in sections)


def notes_for(text: str, version: str) -> str:
    """Plain text of `version`'s section in a What's New file; "" if it has none.

    Groups read "New:" or "Fixed:" followed by "• " bullets, which is how
    TestFlight shows it (it has no Markdown). Only the newest build is wanted,
    so an older section is never returned.
    """
    sections = parse(text)
    if not sections or sections[0].version != version:
        return ""
    lines: list[str] = []
    for title, bullets in sections[0].groups.items():
        if bullets:
            lines += [f"{title}:"] + [f"• {bullet}" for bullet in bullets] + [""]
    return "\n".join(lines).strip()


def read_fragments(folder: Path) -> list[tuple[str, str, str]]:
    """(number, type, text) for each fragment, ordered by number."""
    found = []
    for path in folder.iterdir():
        if match := FRAGMENT.match(path.name):
            text = " ".join(path.read_text(encoding="utf-8").split())
            found.append((match["number"], match["kind"], text))

    def order(item: tuple[str, str, str]) -> tuple[int, str]:
        number = item[0]
        return (int(number), number) if number.isdigit() else (10**9, number)

    return sorted(found, key=order)


def collect(root: Path, version: str, today: date) -> int:
    """Fold the fragments into What's New; returns how many were shown.

    Fragments are deleted once collected, whether they are shown or not.
    """
    if not VERSION.fullmatch(version):
        raise ValueError(f"version must look like 2026.11.3.1: {version}")
    folder = root / "changes"
    fragments = read_fragments(folder) if folder.is_dir() else []
    shown = [(kind, text) for _, kind, text in fragments if kind in SHOWN_AS]
    if shown:
        path = root / WHATS_NEW
        sections = parse(path.read_text(encoding="utf-8")) if path.exists() else []
        if sections and sections[0].day == today:
            section = sections[0]
            section.version = version  # the day's section carries the latest build
        else:
            section = Section(version, today)
            sections.insert(0, section)
        for kind, text in shown:
            section.groups[SHOWN_AS[kind]].append(text)
        cutoff = today - timedelta(days=KEEP_DAYS)
        keep = [
            s for i, s in enumerate(sections) if s.day >= cutoff or i < MIN_SECTIONS
        ]
        moved = [s for s in sections if s not in keep]
        path.write_text(render(keep), encoding="utf-8")
        if moved:
            archive = root / ARCHIVE
            before = (
                parse(archive.read_text(encoding="utf-8")) if archive.exists() else []
            )
            known = {s.version for s in moved}
            archive.write_text(
                render(moved + [s for s in before if s.version not in known]),
                encoding="utf-8",
            )
    for path in folder.iterdir() if folder.is_dir() else []:
        if FRAGMENT.match(path.name):
            path.unlink()
    return len(shown)


def main(argv: list[str] | None = None) -> None:
    """Collect for a version and say what happened."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("version", help="YYYY.M.D.N, the build's version")
    parser.add_argument(
        "--notes",
        action="store_true",
        help="print the build's notes as plain text instead of collecting",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="the project folder",
    )
    parser.add_argument(
        "--today", type=date.fromisoformat, default=None, help="YYYY-MM-DD"
    )
    args = parser.parse_args(argv)
    if args.notes:
        path = args.root / WHATS_NEW
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        print(notes_for(text, args.version))
        return
    count = collect(args.root, args.version, args.today or date.today())
    print(f"Collected {count} change{'' if count == 1 else 's'} for {args.version}")


if __name__ == "__main__":
    main()
