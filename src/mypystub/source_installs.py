"""Fetch and unpack the source a requirement points at (#169, #172, #257).

``foo @ https://host/foo-1.0.tar.gz`` and ``foo @ git+https://github.com/o/r``
(fetched as an archive, see :mod:`git_hosts`) name source, not a wheel. This module turns such a URL into an unpacked project
folder; :mod:`source_build` then builds a wheel from it with the project's own
build backend, in-process, and the wheel is installed like any other.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import re
import shutil
import tarfile
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urldefrag, urlsplit

ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")


class SourceProblem(Exception):
    """Source that can't be used; the message says why, for the user."""


def subdirectory(url: str) -> str:
    """The ``#subdirectory=`` a URL asks for, or "" for the archive's root."""
    values = parse_qs(urldefrag(url).fragment).get("subdirectory", [""])
    return values[0].strip("/")


def ref_of(url: str) -> str:
    """The ref (tag, branch or commit) an archive URL was made for, if it shows."""
    path = urlsplit(urldefrag(url).url).path
    segments = [s for s in path.split("/") if s]
    # GitLab's .../-/archive/<ref>/<repo>-<ref>.zip names the ref in the path
    for index in range(len(segments) - 2):
        if segments[index : index + 2] == ["-", "archive"]:
            return segments[index + 2]
    name = PurePosixPath(path).name
    for suffix in ARCHIVE_SUFFIXES:
        name = name.removesuffix(suffix)
    return name


# -- Unpacking ------------------------------------------------------------


def extract(archive: Path, into: Path) -> Path:
    """Unpack `archive` into the new folder `into`; return the project's root.

    Refuses a path that would leave the folder. If everything is inside one
    top-level folder (as GitHub archives are), that folder is the root.
    """
    into.mkdir(parents=True, exist_ok=True)
    try:
        if zipfile.is_zipfile(archive):
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
                _check_paths(names)
                zf.extractall(into)
        else:
            with tarfile.open(archive) as tf:
                _check_paths(tf.getnames())
                tf.extractall(into, filter="data")
    except (zipfile.BadZipFile, tarfile.TarError, OSError) as error:
        raise SourceProblem(f"{archive.name} can't be unpacked: {error}") from None
    entries = [p for p in into.iterdir() if p.name != "pax_global_header"]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return into


def commit_of(archive: Path) -> str:
    """The commit a GitHub zip was made from, which it keeps as its comment."""
    try:
        with zipfile.ZipFile(archive) as zf:
            comment = zf.comment.decode("ascii", "replace")
    except (zipfile.BadZipFile, OSError):
        return ""
    return comment if re.fullmatch(r"[0-9a-f]{40}", comment) else ""


def open_source(archive: Path, url: str) -> Path:
    """Unpack `archive` beside itself; the project folder `url` points at."""
    unpacked = archive.parent / "unpacked"
    shutil.rmtree(unpacked, ignore_errors=True)
    root = extract(archive, unpacked)
    if sub := subdirectory(url):
        root = (root / sub).resolve()
        if not root.is_relative_to(unpacked.resolve()) or not root.is_dir():
            raise SourceProblem(f"it has no folder called {sub}")
    return root


def _check_paths(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise SourceProblem(f"The archive has an unsafe path: {name}")


# -- Versions a build can't find on its own --------------------------------


def version_from_archival(root: Path) -> str | None:
    """A version from ``.git_archival.txt`` (setuptools_scm's archive support)."""
    path = root / ".git_archival.txt"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    described = re.search(
        r"describe-name:\s*v?(\d[\w.]*)(?:-(\d+)-g[0-9a-f]+)?\s*$", text, re.MULTILINE
    )
    if described:
        base, distance = described.group(1), described.group(2)
        return f"{base}.post{distance}" if distance and distance != "0" else base
    tagged = re.search(r"ref-names:.*?tag:\s*v?(\d[\w.]*)", text)
    return tagged.group(1) if tagged else None


def version_hint(root: Path, url: str, commit: str = "") -> str | None:
    """A version for a build that reads it from Git, which an archive lacks.

    From ``.git_archival.txt``, else the archive's ref (a tag such as ``v1.2``),
    else ``0+g<commit>``, else ``0+unknown``. Version plugins (setuptools-scm, hatch-vcs) are told
    it, as they can't run ``git`` here.
    """
    ref = ref_of(url)
    if re.fullmatch(r"[0-9a-fA-F]{40}", ref):
        ref = ""  # a commit, not a version, even when it starts with a digit
    for text in (version_from_archival(root), ref.removeprefix("v")):
        if text and re.match(r"\d", text):
            return text
    return f"0+g{commit[:7]}" if commit else "0+unknown"
