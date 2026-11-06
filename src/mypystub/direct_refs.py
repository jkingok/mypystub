"""Requirements that point at a URL instead of naming a package on PyPI (#169).

``foo @ https://host/foo-1.0-py3-none-any.whl`` and
``foo @ git+https://github.com/o/r.git@v1`` are valid PEP 508 requirements, but
the resolver only knows how to find packages by name. Without a check, such a
requirement would be installed as the same name from PyPI, which may be a
different project or version. This module recognises them so each kind can be
refused clearly, and supported one kind at a time.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urldefrag, urlsplit

from packaging.requirements import Requirement
from packaging.tags import Tag
from packaging.utils import (
    InvalidWheelFilename,
    canonicalize_name,
    parse_wheel_filename,
)
from packaging.version import Version

from .source_installs import github_archive_url

ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")

# Kinds of direct reference that can be installed. A kind not in here is refused
# with a message that says why (see :func:`unsupported_message`).
SUPPORTED: frozenset[str] = frozenset({"wheel", "archive", "github"})

WHY = {
    "git+https": "installing from this git host isn't supported yet (GitHub is)",
    "git+ssh": "installing from git over SSH isn't supported",
    "git": "this kind of git URL isn't supported",
    "file": "a local file path can't be used, since it won't exist on other devices",
    "other": "this kind of URL isn't supported",
}


def kind_of(url: str) -> str:
    """What a requirement's URL points at.

    One of ``wheel``, ``archive``, ``github`` (a GitHub repository, which is
    fetched as an archive), ``git+https``, ``git+ssh``, ``git`` (any
    other ``git+`` scheme), ``file`` or ``other``.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if github_archive_url(url):
        return "github"
    if scheme.startswith("git+"):
        transport = scheme[len("git+") :]
        if transport in ("https", "http"):
            return "git+https"
        if transport == "ssh":
            return "git+ssh"
        return "git"
    if scheme == "file":
        return "file"
    path = parts.path.lower()
    if path.endswith(".whl"):
        return "wheel"
    if path.endswith(ARCHIVE_SUFFIXES):
        return "archive"
    return "other"


def unsupported_message(requirement: Requirement) -> str | None:
    """Why `requirement` can't be installed, or None if it can.

    A requirement with no URL is an ordinary PyPI name and is always fine.
    """
    if not requirement.url:
        return None
    kind = kind_of(requirement.url)
    if kind in SUPPORTED:
        return None
    return (
        f"Can't install “{requirement}”: {WHY[kind]}. "
        f"Ask for {requirement.name} by name to get it from PyPI, if it's there."
    )


# -- Wheels at a URL (#171) ---------------------------------------------------


class WheelProblem(Exception):
    """A direct wheel URL that can't be used; the message says why."""


def url_filename(url: str) -> str:
    """The file name at the end of a URL's path, without its fragment."""
    return PurePosixPath(unquote(urlsplit(urldefrag(url).url).path)).name


def expected_sha256(url: str) -> str | None:
    """The hash a URL asks for in its ``#sha256=...`` fragment, if any."""
    fragment = urldefrag(url).fragment
    match = re.search(r"(?:^|&)sha256=([0-9a-fA-F]{64})(?:&|$)", fragment)
    return match[1].lower() if match else None


def cache_path(cache_dir: Path, url: str) -> Path:
    """Where a URL's file is kept: its own folder, so same-named files can't clash."""
    key = hashlib.sha256(urldefrag(url).url.encode("utf-8")).hexdigest()[:16]
    return cache_dir / "direct" / key / url_filename(url)


def check_sha256(path: Path, url: str) -> None:
    """Raise WheelProblem if `path` isn't the file `url`'s ``#sha256=`` names."""
    wanted = expected_sha256(url)
    if wanted is None:
        return
    found = hashlib.sha256(path.read_bytes()).hexdigest()
    if found != wanted:
        raise WheelProblem(
            f"{url_filename(url)} doesn't match its sha256 (expected {wanted[:12]}…, "
            f"got {found[:12]}…)."
        )


def wheel_identity(
    requirement: Requirement, supported_tags: Iterable[Tag]
) -> tuple[str, Version]:
    """The (name, version) of the wheel `requirement` points at, after checking it.

    Raises WheelProblem if the file name isn't a wheel's, names a different
    project than the requirement, or has no tag this platform can use.
    """
    assert requirement.url
    filename = url_filename(requirement.url)
    try:
        name, version, _, tags = parse_wheel_filename(filename)
    except InvalidWheelFilename as error:
        raise WheelProblem(
            f"{filename} isn't a valid wheel file name: {error}"
        ) from None
    if name != canonicalize_name(requirement.name):
        raise WheelProblem(
            f"{requirement.name} points at {filename}, which is a wheel for "
            f"{name}, not {requirement.name}."
        )
    if not set(tags) & set(supported_tags):
        raise WheelProblem(
            f"{filename} isn't built for this device (it needs "
            f"{', '.join(sorted(str(t) for t in tags))})."
        )
    return name, version
