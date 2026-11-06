"""Install a pure-Python project from a source archive, without building it (#172).

``foo @ https://host/foo-1.0.tar.gz`` and ``foo @ https://github.com/o/r`` name
source, not a wheel. There is no ``subprocess`` on iOS and nothing compiled may
be installed, so no build backend is run. Instead a project that is plainly pure
Python (see :mod:`purity`) has its package files copied into site-packages and a
``.dist-info`` written from its static ``pyproject.toml`` metadata, which is what
a pure wheel of it would hold. Anything that needs a real build is refused.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import re
import shutil
import tarfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from urllib.parse import parse_qs, urldefrag, urlsplit

from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version

from . import purity, source_metadata
from .source_metadata import SourceProblem

ARCHIVE_SUFFIXES = (".zip", ".tar.gz", ".tgz", ".tar.bz2", ".tar.xz", ".tar")
# Top-level folders that are never the package itself
NOT_PACKAGES = frozenset(
    {"tests", "test", "docs", "doc", "examples", "example", "build", "dist", "scripts"}
)
NOT_MODULES = frozenset({"setup.py", "conftest.py", "noxfile.py", "fabfile.py"})


# -- GitHub ---------------------------------------------------------------


def github_archive_url(url: str) -> str | None:
    """The archive URL for a GitHub repository URL, or None if it isn't one.

    Understands ``https://github.com/o/r``, ``.../r.git``, ``.../tree/<ref>``,
    ``...@<ref>`` and a ``git+`` prefix. With no ref the default branch
    (``HEAD``) is used. The fragment (``#subdirectory=``, ``#sha256=``) is kept.
    """
    base, fragment = urldefrag(url)
    parts = urlsplit(base)
    scheme = parts.scheme.lower().removeprefix("git+")
    if scheme not in ("https", "http") or parts.netloc.lower() not in (
        "github.com",
        "www.github.com",
    ):
        return None
    path, _, at = parts.path.partition("@")
    segments = [s for s in path.split("/") if s]
    if len(segments) < 2:
        return None
    owner, repo = segments[0], segments[1].removesuffix(".git")
    ref = at
    if len(segments) >= 4 and segments[2] == "tree":
        ref = "/".join(segments[3:])
    elif len(segments) != 2:
        return None  # a file, an issue, a release page: not a repository root
    if not owner or not repo:
        return None
    archive = f"https://github.com/{owner}/{repo}/archive/{ref or 'HEAD'}.zip"
    return f"{archive}#{fragment}" if fragment else archive


def subdirectory(url: str) -> str:
    """The ``#subdirectory=`` a URL asks for, or "" for the archive's root."""
    values = parse_qs(urldefrag(url).fragment).get("subdirectory", [""])
    return values[0].strip("/")


def ref_of(url: str) -> str:
    """The ref (tag, branch or commit) an archive URL was made for, if it shows."""
    path = urlsplit(urldefrag(url).url).path
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


def open_archive(archive: Path, url: str, name: str | None = None) -> Project:
    """Unpack `archive` beside itself and read the project `url` points at."""
    unpacked = archive.parent / "unpacked"
    shutil.rmtree(unpacked, ignore_errors=True)
    root = extract(archive, unpacked)
    if sub := subdirectory(url):
        root = (root / sub).resolve()
        if not root.is_relative_to(unpacked.resolve()) or not root.is_dir():
            raise SourceProblem(f"it has no folder called {sub}")
    return read_project(root, url, name, commit_of(archive))


def _check_paths(names: list[str]) -> None:
    for name in names:
        path = PurePosixPath(name.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts:
            raise SourceProblem(f"The archive has an unsafe path: {name}")


# -- Reading a project ----------------------------------------------------


@dataclass
class Project:
    """A pure-Python project found in an unpacked archive."""

    root: Path
    name: str
    version: Version
    requires: list[str]
    requires_python: str
    summary: str
    entry_points: dict[str, dict[str, str]]
    packages: list[Path]
    url: str
    extras: dict[str, list[str]] = field(default_factory=dict)
    # Files a build would have written: path in site-packages -> text
    generated: dict[str, str] = field(default_factory=dict)

    def metadata_text(self) -> str:
        """The project as a wheel's METADATA, so its dependencies can be resolved."""
        lines = [
            "Metadata-Version: 2.1",
            f"Name: {self.name}",
            f"Version: {self.version}",
        ]
        if self.summary:
            lines.append(f"Summary: {self.summary}")
        if self.requires_python:
            lines.append(f"Requires-Python: {self.requires_python}")
        lines += [f"Requires-Dist: {r}" for r in self.requires]
        for extra, requirements in sorted(self.extras.items()):
            lines.append(f"Provides-Extra: {extra}")
            for requirement in requirements:
                if ";" in requirement:
                    base, marker = requirement.split(";", 1)
                    lines.append(
                        f"Requires-Dist: {base.strip()}; "
                        f"({marker.strip()}) and extra == '{extra}'"
                    )
                else:
                    lines.append(f"Requires-Dist: {requirement}; extra == '{extra}'")
        return "\n".join(lines) + "\n"


def _version_from_archival(root: Path) -> str | None:
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


def _version(
    project: dict, data: dict, root: Path, url: str, commit: str = ""
) -> Version:
    candidates = []
    if isinstance(project.get("version"), str):
        candidates.append(project["version"])
    candidates.append(source_metadata.named_version(root, data, project["name"]))
    candidates.append(_version_from_archival(root) or "")
    candidates.append(ref_of(url).removeprefix("v"))
    for text in candidates:
        try:
            if text:
                return Version(text)
        except InvalidVersion:
            continue
    return Version(f"0+g{commit[:7]}" if commit else "0+unknown")


def version_is_unknown(version: Version) -> bool:
    """Whether `version` only stands in for one the source doesn't say."""
    return version.public == "0" and version.local is not None


def _generated_files(
    root: Path, data: dict, packages: list[Path], version: Version
) -> dict[str, str]:
    """The version file setuptools_scm would write, which packages may import."""
    file = source_metadata.version_file(root, data)
    if not file:
        return {}
    path = (root / file).resolve()
    release = ", ".join(str(n) for n in version.release)
    text = f'__version__ = version = "{version}"\n'
    text += f"__version_tuple__ = version_tuple = ({release},)\n"
    for package in packages:
        if path.is_relative_to(package.resolve()):
            return {path.relative_to(package.resolve().parent).as_posix(): text}
    return {}


def _find_packages(root: Path, project: dict) -> list[Path]:
    """The package folders and modules to install: as named, else by their layout."""
    if declared := source_metadata.declared_packages(root, project):
        return declared
    src = root / "src"
    where = (
        project.get("tool", {})
        .get("setuptools", {})
        .get("packages", {})
        .get("find", {})
        .get("where")
    )
    base = root / where[0] if where else src if src.is_dir() else root
    found: list[Path] = []
    for entry in sorted(base.iterdir()):
        name = entry.name
        if name.startswith((".", "_")) and name != "__init__.py":
            continue
        if entry.is_dir():
            if base == root and (name in NOT_PACKAGES or name.endswith(".egg-info")):
                continue
            # In src, a namespace package needn't have Python at its top level
            namespace = base != root and any(entry.rglob("*.py"))
            if (entry / "__init__.py").exists() or any(entry.glob("*.py")) or namespace:
                found.append(entry)
        elif name.endswith(".py") and name not in NOT_MODULES:
            found.append(entry)
    return found


def read_project(
    root: Path, url: str, name: str | None = None, commit: str = ""
) -> Project:
    """Read the project at `root`; raise SourceProblem if it can't be installed here.

    `commit` is the commit it came from, if known, to stand in for a version.
    """
    data = source_metadata.read_pyproject(root)
    # Checked first, so a compiled project is refused for being compiled
    if reason := purity.tree_impurity(root, data, []):
        raise SourceProblem(reason)
    project = source_metadata.declared_project(root, data)
    dynamic = set(project.get("dynamic", []))
    unreadable = dynamic - {"version", "readme"}
    if unreadable:
        names = sorted(unreadable)
        verb = "are" if len(names) > 1 or names[0].endswith("s") else "is"
        raise SourceProblem(
            f"its {' and '.join(names)} {verb} worked out by a build, "
            "which isn't run here"
        )
    packages = _find_packages(root, data)
    if not packages:
        raise SourceProblem("no Python package was found in it to install")
    if reason := purity.tree_impurity(root, data, packages):
        raise SourceProblem(reason)
    project_name = str(project["name"])
    if name and canonicalize_name(project_name) != canonicalize_name(name):
        raise SourceProblem(f"it is the project {project_name}, not {name}")
    entry_points: dict[str, dict[str, str]] = {
        group: dict(points) for group, points in project.get("entry-points", {}).items()
    }
    if project.get("scripts"):
        entry_points["console_scripts"] = dict(project["scripts"])
    if project.get("gui-scripts"):
        entry_points["gui_scripts"] = dict(project["gui-scripts"])
    version = _version(project, data, root, url, commit)
    return Project(
        root=root,
        name=project_name,
        version=version,
        requires=[str(r) for r in project.get("dependencies", [])],
        requires_python=str(project.get("requires-python") or ""),
        summary=str(project.get("description") or ""),
        entry_points=entry_points,
        packages=packages,
        url=url,
        extras={
            str(extra): [str(r) for r in reqs]
            for extra, reqs in project.get("optional-dependencies", {}).items()
        },
        generated=_generated_files(root, data, packages, version),
    )


# -- Installing -----------------------------------------------------------


def _record_line(path: str, data: bytes) -> list[str]:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=")
    return [path, f"sha256={digest.decode()}", str(len(data))]


def install(project: Project, target: Path) -> None:
    """Copy the project's packages into `target` and write its ``.dist-info``."""
    records: list[list[str]] = []
    for package in project.packages:
        if package.is_file():
            destination = target / package.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(package, destination)
            records.append(_record_line(package.name, destination.read_bytes()))
            continue
        for file in sorted(package.rglob("*")):
            if not file.is_file() or "__pycache__" in file.parts:
                continue
            relative = file.relative_to(package.parent)
            destination = target / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(file, destination)
            records.append(_record_line(relative.as_posix(), destination.read_bytes()))
    for relative, text in project.generated.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")
        records.append(_record_line(relative, text.encode()))
    distribution = canonicalize_name(project.name).replace("-", "_")
    info_name = f"{distribution}-{project.version}.dist-info"
    info = target / info_name
    info.mkdir(parents=True, exist_ok=True)
    files = {
        "METADATA": project.metadata_text().encode(),
        "WHEEL": (
            b"Wheel-Version: 1.0\nGenerator: mypystub-source-install\n"
            b"Root-Is-Purelib: true\nTag: py3-none-any\n"
        ),
        "INSTALLER": b"mypystub\n",
        "direct_url.json": json.dumps(
            {"url": urldefrag(project.url).url, "archive_info": {}}
        ).encode(),
    }
    if project.entry_points:
        text = ""
        for group, points in sorted(project.entry_points.items()):
            text += f"[{group}]\n" + "".join(f"{k} = {v}\n" for k, v in points.items())
            text += "\n"
        files["entry_points.txt"] = text.encode()
    for name, data in files.items():
        (info / name).write_bytes(data)
        records.append(_record_line(f"{info_name}/{name}", data))
    records.append([f"{info_name}/RECORD", "", ""])
    out = io.StringIO()
    csv.writer(out, lineterminator="\n").writerows(records)
    (info / "RECORD").write_text(out.getvalue(), encoding="utf-8")
