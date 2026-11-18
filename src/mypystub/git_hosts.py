"""``git+https://`` requirements on major git hosts, fetched as archives (#286).

pip installs ``foo @ git+https://github.com/o/r@v1`` by cloning it with git.
Phones have no git, so MyPyStub's own installer downloads the same ref as an
archive from the host instead. It understands only pip's official form,
``git+https://<host>/<repository>[.git][@<ref>][#<fragment>]``, so a
requirement works the same with pip (desktop Native mode) and on a phone:

=========  ============================================================
GitHub     ``https://github.com/<owner>/<repo>/archive/<ref>.zip``
GitLab     ``https://gitlab.com/<group/.../repo>/-/archive/<ref>/<repo>-<ref>.zip``
Bitbucket  ``https://bitbucket.org/<workspace>/<repo>/get/<ref>.zip``
=========  ============================================================

With no ref, ``HEAD`` (the default branch) is used. Fragments such as
``#subdirectory=`` are kept. A repository's web page (``https://github.com/o/r``,
``.../tree/<ref>``) isn't installable by pip, so it isn't accepted either:
:func:`page_suggestion` gives the ``git+https://`` form to use instead.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

from collections.abc import Callable
from urllib.parse import urldefrag, urlsplit


def _github(parts: list[str], ref: str) -> str | None:
    if len(parts) != 2:
        return None
    owner, repo = parts
    return f"https://github.com/{owner}/{repo}/archive/{ref}.zip"


def _gitlab(parts: list[str], ref: str) -> str | None:
    # Groups can nest: gitlab.com/group/subgroup/repo
    if len(parts) < 2:
        return None
    path, repo = "/".join(parts), parts[-1]
    return f"https://gitlab.com/{path}/-/archive/{ref}/{repo}-{ref}.zip"


def _bitbucket(parts: list[str], ref: str) -> str | None:
    if len(parts) != 2:
        return None
    workspace, repo = parts
    return f"https://bitbucket.org/{workspace}/{repo}/get/{ref}.zip"


HOSTS: dict[str, Callable[[list[str], str], str | None]] = {
    "github.com": _github,
    "gitlab.com": _gitlab,
    "bitbucket.org": _bitbucket,
}


def host_of(netloc: str) -> str | None:
    """The supported host a URL's network location names, or None."""
    host = netloc.lower().rpartition("@")[2].removeprefix("www.")
    return host if host in HOSTS else None


def archive_url(url: str) -> str | None:
    """The archive URL for a ``git+https://`` URL on a supported host, else None."""
    base, fragment = urldefrag(url)
    parts = urlsplit(base)
    if parts.scheme.lower() not in ("git+https", "git+http"):
        return None
    host = host_of(parts.netloc)
    if host is None:
        return None
    path, _, ref = parts.path.partition("@")
    segments = [s for s in path.split("/") if s]
    if segments:
        segments[-1] = segments[-1].removesuffix(".git")
    if not all(segments):
        return None
    archive = HOSTS[host](segments, ref or "HEAD")
    if archive is None:
        return None
    return f"{archive}#{fragment}" if fragment else archive


def page_suggestion(url: str) -> str | None:
    """For a repository's web page on a supported host, the pip form to use.

    ``https://github.com/o/r`` and ``https://github.com/o/r/tree/v1`` give
    ``git+https://github.com/o/r`` and ``git+https://github.com/o/r@v1``.
    None for anything else, including archive and file URLs.
    """
    base, fragment = urldefrag(url)
    parts = urlsplit(base)
    if parts.scheme.lower() not in ("https", "http"):
        return None
    host = host_of(parts.netloc)
    if host is None:
        return None
    segments = [s for s in parts.path.split("/") if s]
    ref = ""
    if host == "gitlab.com":
        # gitlab.com/group/sub/repo, or .../repo/-/tree/<ref>; nothing else
        if "-" in segments:
            index = segments.index("-")
            if segments[index + 1 : index + 2] != ["tree"]:
                return None
            ref = "/".join(segments[index + 2 :])
            segments = segments[:index]
        if len(segments) < 2:
            return None
    else:
        # owner/repo, or owner/repo/tree/<ref> (GitHub), owner/repo/src/<ref>
        marker = "tree" if host == "github.com" else "src"
        if len(segments) > 3 and segments[2] == marker:
            ref = "/".join(segments[3:])
            segments = segments[:2]
        if len(segments) != 2:
            return None
    segments[-1] = segments[-1].removesuffix(".git")
    suggestion = f"git+https://{host}/{'/'.join(segments)}"
    if ref:
        suggestion += f"@{ref}"
    return f"{suggestion}#{fragment}" if fragment else suggestion
