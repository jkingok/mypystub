"""Helpers for tests that build source archives and wheels on the fly."""

import io
import zipfile
from pathlib import Path
from typing import Any, cast

import httpx2
import resolvelib
from packaging.requirements import Requirement
from packaging.tags import Tag
from packaging.version import Version

from mypystub import piplike

ANY = {Tag("py3", "none", "any")}
# The project's one dependency, bundled in the app (so nothing is fetched)
BUNDLED = {"somelib": Version("1.0")}

TOGA_CONSOLE_LIKE = {
    "pyproject.toml": """
[build-system]
requires = ["fakebackend==1.0"]
build-backend = "fakebackend"

[project]
dynamic = ["version"]
name = "toga-console"
description = "A console widget"
requires-python = ">=3.10"
dependencies = ["toga-core >= 0.5.7, < 0.6"]

[project.optional-dependencies]
extra = ["rich>=13; python_version >= '3.10'"]

[project.entry-points."toga_console.backend.toga_dummy"]
Console = "toga_console.platforms.dummy:Console"

[tool.setuptools_scm]
""",
    ".git_archival.txt": "node: abc123\ndescribe-name: v0.1.0\nref-names: tag: v0.1.0\n",
    "src/toga_console/__init__.py": "VALUE = 'console'\n",
    "src/toga_console/platforms/__init__.py": "",
    "src/toga_console/platforms/dummy.py": "class Console: ...\n",
    "src/toga_console/data/hello.txt": "hello\n",
    "tests/test_x.py": "def test(): ...\n",
    "examples/demo/app.py": "print('demo')\n",
}


# A tiny PEP 517 backend, standing in for setuptools and friends so tests need
# no network: it packages the top-level packages (under src/ if there is one)
# with static [project] metadata, takes a dynamic version from the variable
# version plugins read, and fails like setuptools (SystemExit) on C sources.
FAKE_BACKEND = r"""
import os, re, tomllib, zipfile
from pathlib import Path

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    project = tomllib.loads(Path("pyproject.toml").read_text())["project"]
    version = project.get("version") or os.environ.get("SETUPTOOLS_SCM_PRETEND_VERSION")
    if not version:
        raise LookupError("unable to detect version")
    if any(Path().rglob("*.c")):
        raise SystemExit("error: command 'cc' failed: no compiler")
    name = re.sub(r"[-_.]+", "_", project["name"]).lower()
    base = Path("src") if Path("src").is_dir() else Path(".")
    packages = [p for p in base.iterdir() if (p / "__init__.py").exists()]
    info = f"{name}-{version}.dist-info"
    lines = ["Metadata-Version: 2.1", f"Name: {project['name']}", f"Version: {version}"]
    lines += [f"Requires-Dist: {r}" for r in project.get("dependencies", [])]
    for extra, reqs in project.get("optional-dependencies", {}).items():
        lines.append(f"Provides-Extra: {extra}")
        lines += [f"Requires-Dist: {r.split(';')[0].strip()}; extra == '{extra}'" for r in reqs]
    points = []
    for group, entries in project.get("entry-points", {}).items():
        points.append(f"[{group}]")
        points += [f"{k} = {v}" for k, v in entries.items()]
    wheel = Path(wheel_directory) / f"{name}-{version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        record = []
        for package in packages:
            for file in package.rglob("*"):
                if file.is_file() and "__pycache__" not in file.parts:
                    arc = file.relative_to(base).as_posix()
                    zf.write(file, arc)
                    record.append(arc)
        for arc, text in (
            (f"{info}/METADATA", "\n".join(lines) + "\n"),
            (f"{info}/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n"),
            (f"{info}/entry_points.txt", "\n".join(points) + "\n"),
        ):
            zf.writestr(arc, text)
            record.append(arc)
        zf.writestr(f"{info}/RECORD", "".join(f"{r},,\n" for r in record + [f"{info}/RECORD"]))
    return wheel.name
"""


def install_fake_backend(requires: tuple[str, ...], site: Path) -> None:
    """The backend installer tests use: the fake backend, whatever is asked for."""
    (site / "fakebackend.py").write_text(FAKE_BACKEND)


def make_zip(files: dict[str, str | bytes], top: str = "project-main") -> bytes:
    """A zip of `files` inside one top-level folder, as GitHub makes them."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(f"{top}/{name}" if top else name, content)
    return buffer.getvalue()


def write_tree(root: Path, files: dict[str, str | bytes]) -> Path:
    """Write `files` under `root`; return it."""
    for name, content in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content if isinstance(content, bytes) else content.encode())
    return root


def serve(served: dict[str, bytes]) -> httpx2.MockTransport:
    """A transport serving `served` (URL without fragment -> bytes)."""

    def handler(request: httpx2.Request) -> httpx2.Response:
        url = str(request.url.copy_with(fragment=None))
        return (
            httpx2.Response(200, content=served[url])
            if url in served
            else httpx2.Response(404)
        )

    return httpx2.MockTransport(handler)


def provider(tmp_path: Path, served: dict[str, bytes], **kwargs: Any):
    """A provider with no index, whose HTTP client serves `served`."""
    return piplike.PyPIWheelProvider(
        finder=cast(Any, None),
        cache_dir=tmp_path / "cache",
        system_packages=kwargs.pop("system", {}),
        http_client=httpx2.Client(transport=serve(served)),
        supported_tags=ANY,
        backend_installer=kwargs.pop("backend_installer", install_fake_backend),
        **kwargs,
    )


def resolve(p: piplike.PyPIWheelProvider, *requirements: str) -> dict[str, Any]:
    """Resolve, returning the pinned candidates by name."""
    resolver = resolvelib.Resolver(p, resolvelib.BaseReporter())
    return dict(resolver.resolve([Requirement(r) for r in requirements]).mapping)
