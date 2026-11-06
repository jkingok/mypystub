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
requires = ["setuptools==84.2.1", "setuptools_scm==10.3.4"]
build-backend = "setuptools.build_meta"

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
        **kwargs,
    )


def resolve(p: piplike.PyPIWheelProvider, *requirements: str) -> dict[str, Any]:
    """Resolve, returning the pinned candidates by name."""
    resolver = resolvelib.Resolver(p, resolvelib.BaseReporter())
    return dict(resolver.resolve([Requirement(r) for r in requirements]).mapping)
