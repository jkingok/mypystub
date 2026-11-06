"""Source archives and GitHub URLs in requirements, and the purity rule (#172)."""

import asyncio
import importlib
import sys
import zipfile
from pathlib import Path
from typing import Any

import httpx2
import pytest
from packaging.version import Version

from mypystub import piplike
from tests.support_sources import (
    BUNDLED,
    TOGA_CONSOLE_LIKE,
    make_zip,
    provider,
    resolve,
    serve,
)

ARCHIVE = "https://github.com/beeware/toga-console/archive/HEAD.zip"
CONSOLE = {
    **TOGA_CONSOLE_LIKE,
    "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"].replace(
        "toga-core >= 0.5.7, < 0.6", "somelib>=1"
    ),
}


def test_a_github_url_resolves_to_the_project_in_its_archive(tmp_path: Path) -> None:
    """The URL is turned into an archive URL; the project is read, not built."""
    served = {ARCHIVE: make_zip(CONSOLE)}
    p = provider(tmp_path, served, system=BUNDLED)
    pinned = resolve(p, "toga-console @ https://github.com/beeware/toga-console")
    candidate = pinned["toga-console"]
    assert candidate.version == Version("0.1.0")
    assert candidate.is_direct and candidate.source_root is not None
    assert pinned["somelib"].is_system  # its dependency came from pyproject


def test_git_https_on_github_needs_no_git(tmp_path: Path) -> None:
    """``git+https://github.com/...@ref`` is fetched as that ref's archive."""
    url = "https://github.com/beeware/toga-console/archive/v0.1.0.zip"
    p = provider(
        tmp_path,
        {url: make_zip(CONSOLE)},
        system=BUNDLED,
    )
    pinned = resolve(
        p, "toga-console @ git+https://github.com/beeware/toga-console.git@v0.1.0"
    )
    assert pinned["toga-console"].version == Version("0.1.0")


def test_subdirectory_is_honoured(tmp_path: Path) -> None:
    """``#subdirectory=`` picks the project inside a larger repository."""
    files = {f"packages/console/{k}": v for k, v in CONSOLE.items()}
    files["README.md"] = "monorepo"
    p = provider(tmp_path, {ARCHIVE: make_zip(files)}, system=BUNDLED)
    pinned = resolve(
        p,
        "toga-console @ https://github.com/beeware/toga-console#subdirectory=packages/console",
    )
    assert "toga-console" in pinned
    with pytest.raises(piplike.DependencyError, match="no folder called nope"):
        resolve(
            provider(tmp_path / "b", {ARCHIVE: make_zip(files)}),
            "toga-console @ https://github.com/beeware/toga-console#subdirectory=nope",
        )


def test_a_plain_archive_url_works_too(tmp_path: Path) -> None:
    """A .tar.gz-style URL, not just GitHub's."""
    url = "https://files.example/toga-console-0.1.0.zip"
    p = provider(
        tmp_path,
        {url: make_zip(CONSOLE)},
        system=BUNDLED,
    )
    assert resolve(p, f"toga-console @ {url}")["toga-console"].is_direct


@pytest.mark.parametrize(
    ("files", "fragment"),
    [
        (
            {
                **TOGA_CONSOLE_LIKE,
                "src/toga_console/_speed.so": b"binary",
            },
            "_speed.so",
        ),
        (
            {
                **TOGA_CONSOLE_LIKE,
                "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"].replace(
                    "setuptools.build_meta", "maturin"
                ),
            },
            "compiles code",
        ),
    ],
)
def test_source_that_needs_a_build_is_refused_in_a_dialog_sized_message(
    tmp_path: Path, files: dict, fragment: str
) -> None:
    """The message names the requirement and what needs a build."""
    p = provider(tmp_path, {ARCHIVE: make_zip(files)})
    with pytest.raises(piplike.DependencyError, match="Can't install") as error:
        resolve(p, "toga-console @ https://github.com/beeware/toga-console")
    assert fragment in str(error.value)


def test_a_sha256_on_an_archive_is_checked(tmp_path: Path) -> None:
    """A wrong hash is refused, and the file is not kept."""
    p = provider(tmp_path, {ARCHIVE: make_zip(CONSOLE)})
    with pytest.raises(piplike.DependencyError, match="sha256"):
        resolve(
            p,
            f"toga-console @ https://github.com/beeware/toga-console#sha256={'0' * 64}",
        )


def install(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    served: dict[str, bytes],
    requirement: str,
    **kwargs: Any,
) -> Path:
    """Run resolve_and_install_async against `served`; return the target."""
    transport = serve(served)
    real_client, real_async = httpx2.Client, httpx2.AsyncClient
    monkeypatch.setattr(
        piplike.httpx2, "Client", lambda **kw: real_client(transport=transport, **kw)
    )
    monkeypatch.setattr(
        piplike.httpx2,
        "AsyncClient",
        lambda **kw: real_async(transport=transport, **kw),
    )
    target = tmp_path / "site"
    asyncio.run(
        piplike.resolve_and_install_async(
            [requirement], target, cache_dir=tmp_path / "cache", **kwargs
        )
    )
    return target


def test_install_from_github_makes_it_importable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end: fetch, read, copy, and import. The dependency is bundled."""
    files = dict(TOGA_CONSOLE_LIKE)
    files["pyproject.toml"] = files["pyproject.toml"].replace(
        'dependencies = ["toga-core >= 0.5.7, < 0.6"]', "dependencies = []"
    )
    target = install(
        tmp_path,
        monkeypatch,
        {ARCHIVE: make_zip(files)},
        "toga-console @ https://github.com/beeware/toga-console",
        use_system=False,
    )
    monkeypatch.syspath_prepend(str(target))
    for name in [n for n in sys.modules if n.startswith("toga_console")]:
        monkeypatch.delitem(sys.modules, name)
    importlib.invalidate_caches()
    assert importlib.import_module("toga_console").VALUE == "console"


def impure_wheel() -> bytes:
    """A wheel tagged any that says it isn't pure."""
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as wheel:
        wheel.writestr("foo.py", "x = 1\n")
        wheel.writestr(
            "foo-1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: foo\nVersion: 1.0\n",
        )
        wheel.writestr(
            "foo-1.0.dist-info/WHEEL", "Wheel-Version: 1.0\nRoot-Is-Purelib: false\n"
        )
    return buffer.getvalue()


def test_an_impure_wheel_is_refused_when_pure_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The purity rule applies to wheels from a URL too, and nothing is unpacked."""
    url = "https://files.example/foo-1.0-py3-none-any.whl"
    with pytest.raises(piplike.DependencyError, match="Root-Is-Purelib"):
        install(
            tmp_path,
            monkeypatch,
            {url: impure_wheel()},
            f"foo @ {url}",
            use_system=False,
            pure_only=True,
        )
    assert not (tmp_path / "site" / "foo.py").exists()


def test_pure_only_defaults_to_on_for_ios(monkeypatch: pytest.MonkeyPatch) -> None:
    """Off the device the rule is opt-in; on iOS it is always on."""
    import inspect

    source = inspect.getsource(piplike.resolve_and_install_async)
    assert 'sys.platform == "ios" if pure_only is None else pure_only' in source
