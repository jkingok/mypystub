"""Stamp a release version into pyproject.toml before Briefcase builds (#61).

Fastlane runs this before ``briefcase create``/``update``, so the app's Python
metadata (``toga.App.version``, the About page) carries the same version as the
Xcode project. Fastlane restores pyproject.toml afterwards.

One calver and build number give every form. Python gets the build number as
a fourth release number, so its version is plain PEP 440 numbers, no words:

====================  ===============
Python version        ``2026.11.2.3``
CFBundleShortVersion  ``2026.11.2``
CFBundleVersion       ``3``
====================  ===============

Xcode's version keys hold at most three numbers, so it keeps the date and the
build number apart.

Usage::

    uv run scripts/set_version.py 2026.11.2 3
"""

import argparse
import re
from pathlib import Path

import tomlkit

# YYYY.M.D without leading zeros: PEP 440's normal form, and what Xcode gets
CALVER = re.compile(r"\d{4}\.[1-9]\d?\.[1-9]\d?")


def python_version(calver: str, build: int) -> str:
    """The PEP 440 version for a build: ``<calver>.<build>``, e.g. ``2026.11.2.3``.

    Raises ValueError for a calver with leading zeros (it would differ between
    Xcode and Python) or a build number below 1.
    """
    if not CALVER.fullmatch(calver):
        raise ValueError(f"calver must be YYYY.M.D without leading zeros: {calver}")
    if build < 1:
        raise ValueError(f"build number must be 1 or more: {build}")
    return f"{calver}.{build}"


def stamp(pyproject: str, version: str, build: int) -> str:
    """Set the project and Briefcase versions, and Briefcase's build number.

    Comments and formatting elsewhere in the file are kept.
    """
    doc = tomlkit.parse(pyproject)
    doc["project"]["version"] = version  # type: ignore[index]
    briefcase = doc["tool"]["briefcase"]  # type: ignore[index]
    briefcase["version"] = version  # type: ignore[index]
    briefcase["build"] = build  # type: ignore[index]
    return tomlkit.dumps(doc)


def main(argv: list[str] | None = None) -> None:
    """Stamp pyproject.toml and print the Python version."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("calver", help="YYYY.M.D, e.g. 2026.11.2")
    parser.add_argument("build", type=int, help="build number (CFBundleVersion)")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "pyproject.toml",
    )
    args = parser.parse_args(argv)
    version = python_version(args.calver, args.build)
    path: Path = args.pyproject
    path.write_text(stamp(path.read_text(encoding="utf-8"), version, args.build))
    print(version)


if __name__ == "__main__":
    main()
