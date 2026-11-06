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

from urllib.parse import urlsplit

from packaging.requirements import Requirement

ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")

# Kinds of direct reference that can be installed. A kind not in here is refused
# with a message that says why (see :func:`unsupported_message`).
SUPPORTED: frozenset[str] = frozenset()

WHY = {
    "wheel": "installing a wheel from a URL isn't supported yet",
    "archive": "installing a source archive from a URL isn't supported yet",
    "git+https": "installing from a git repository isn't supported yet",
    "git+ssh": "installing from git over SSH isn't supported",
    "git": "this kind of git URL isn't supported",
    "file": "a local file path can't be used, since it won't exist on other devices",
    "other": "this kind of URL isn't supported",
}


def kind_of(url: str) -> str:
    """What a requirement's URL points at.

    One of ``wheel``, ``archive``, ``git+https``, ``git+ssh``, ``git`` (any
    other ``git+`` scheme), ``file`` or ``other``.
    """
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
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
