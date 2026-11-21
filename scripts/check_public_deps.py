"""Fail if main would depend on a private ``*-internal`` repository.

Some projects come in pairs: a private ``<name>-internal`` repository where the
work happens, and a public ``<name>`` one that its ``main`` and release tags
are mirrored to (``togax-jkingok-internal`` and ``togax-jkingok``, like this
repository and ``mypystub``). ``main`` is mirrored to the public repository,
and built by anyone from there, so it may depend only on public repositories.
A feature branch may use an internal branch while the two are developed
together; this check stops it reaching ``main`` that way.

The PR gate runs it for pull requests into ``main``:

    python scripts/check_public_deps.py

Exits 0 when nothing names an internal repository, 1 (listing where) when
something does. It reads the dependency files only, with the standard library.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Where dependencies are declared or locked: the app, and the project template
DEPENDENCY_FILES = (
    "pyproject.toml",
    "uv.lock",
    "src/mypystub/resources/templates/project/pyproject.toml",
)
# A repository URL whose name ends in -internal (git+https, https, ssh, scp)
INTERNAL = re.compile(
    r"(?:github\.com|gitlab\.com|bitbucket\.org)[/:][\w.-]+/[\w.-]+-internal\b",
    re.IGNORECASE,
)


def internal_references(text: str) -> list[tuple[int, str]]:
    """Line numbers and repositories of every internal repository named."""
    return [
        (number, match.group(0))
        for number, line in enumerate(text.splitlines(), 1)
        for match in INTERNAL.finditer(line)
    ]


def problems(root: Path = ROOT, files: Iterable[str] = DEPENDENCY_FILES) -> list[str]:
    """``file:line: repository`` for each internal repository in `files`."""
    found: list[str] = []
    for name in files:
        path = root / name
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            found += [
                f"{name}:{number}: {repo}" for number, repo in internal_references(text)
            ]
    return found


def main() -> int:
    """Report internal dependencies; the exit status says whether there were any."""
    found = problems()
    if found:
        print("main may depend only on public repositories, but these are internal:")
        print("\n".join(f"  {line}" for line in found))
        print("Point them at the public repository (and a released tag) first.")
        return 1
    print("No internal repositories in the dependencies.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
