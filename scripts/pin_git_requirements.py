"""Pin git requirements to their current commit for one build.

Briefcase installs requirements with pip, and pyproject.toml takes Toga from its
git repository (``toga-core @ git+https://github.com/beeware/toga.git#...``).
pip can't tell whether a branch has moved, so it clones the repository and
builds a new wheel for every package from it, on every install: six clones of
Toga for each ``briefcase create ios``. With a commit in the URL
(``toga.git@<sha>#...``) the wheel can't change, so pip keeps it in its cache
and later builds skip the clone.

Fastlane runs this before ``briefcase create``, alongside set_version.py, and
restores pyproject.toml afterwards, so each build still gets the newest commit.

Usage::

    uv run scripts/pin_git_requirements.py [--pyproject pyproject.toml]
"""

import argparse
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

# A git requirement URL with no revision yet, up to its #fragment or quote
UNPINNED = re.compile(r"git\+(?P<url>https?://[^\s\"'#@]+?\.git)(?=[#\"'])")
SHA = re.compile(r"[0-9a-f]{40}")


def unpinned_urls(pyproject: str) -> list[str]:
    """Each repository URL that a requirement takes without a revision, once."""
    return list(dict.fromkeys(m["url"] for m in UNPINNED.finditer(pyproject)))


def pin(pyproject: str, commits: dict[str, str]) -> str:
    """Add ``@<commit>`` to each unpinned git URL that ``commits`` has.

    Requirements that already name a revision, and the rest of the file, are
    left as they are.
    """

    def add_commit(match: re.Match[str]) -> str:
        url = match["url"]
        commit = commits.get(url)
        return f"git+{url}@{commit}" if commit else match[0]

    return UNPINNED.sub(add_commit, pyproject)


def head_commit(url: str) -> str:
    """The commit a repository's default branch is on, from ``git ls-remote``.

    Raises ValueError when git's answer has no commit in it.
    """
    output = subprocess.run(
        ["git", "ls-remote", url, "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    commit = output.split()[0] if output.split() else ""
    if not SHA.fullmatch(commit):
        raise ValueError(f"git ls-remote gave no commit for {url}: {output!r}")
    return commit


def pin_file(path: Path, resolve: Callable[[str], str] = head_commit) -> dict[str, str]:
    """Pin the git requirements in ``path``, returning each URL's commit."""
    text = path.read_text(encoding="utf-8")
    commits = {url: resolve(url) for url in unpinned_urls(text)}
    path.write_text(pin(text, commits), encoding="utf-8")
    return commits


def main(argv: list[str] | None = None) -> None:
    """Pin pyproject.toml's git requirements and print what each got."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "pyproject.toml",
    )
    args = parser.parse_args(argv)
    for url, commit in pin_file(args.pyproject).items():
        print(f"{url} @ {commit}")


if __name__ == "__main__":
    main()
