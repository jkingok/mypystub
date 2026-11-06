"""A refused package leaves nothing behind, and unknown versions don't block (#172)."""

import asyncio
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from mypystub import piplike
from tests.support_sources import make_zip, provider, resolve

PY = "https://example.com/a-1.0-py3-none-any.whl"
BIN = "https://example.com/b-1.0-cp315-cp315-ios_13_0_arm64_iphoneos.whl"


def test_a_source_with_no_version_satisfies_a_limit_on_it(tmp_path: Path) -> None:
    """You pointed at it, and its version is unknown, not wrong."""
    pyproject = (
        '[build-system]\nrequires = ["setuptools"]\n'
        'build-backend = "setuptools.build_meta"\n'
        '[project]\nname = "thing"\ndynamic = ["version"]\n'
    )
    url = "https://github.com/o/thing/archive/HEAD.zip"
    served = {url: make_zip({"pyproject.toml": pyproject, "thing/__init__.py": ""})}
    p = provider(tmp_path, served)
    pins = resolve(p, "thing @ https://github.com/o/thing", "thing>=2")
    assert str(pins["thing"].version).startswith("0+")


def test_is_satisfied_only_excuses_unknown_versions(tmp_path: Path) -> None:
    """A known version still has to fit."""
    p = provider(tmp_path, {})
    candidate: Any = piplike.Candidate(
        name="thing",
        version=Version("1.0"),
        link=piplike.Link("https://example.com/thing.zip"),
        is_direct=True,
        source_root=tmp_path,
        identifier=canonicalize_name("thing"),
    )
    assert not p.is_satisfied_by(Requirement("thing>=2"), candidate)


def wheel_bytes(name: str, tag: str) -> bytes:
    """A small wheel."""
    import io
    import zipfile

    buffer = io.BytesIO()
    info = f"{name}-1.0.dist-info"
    with zipfile.ZipFile(buffer, "w") as wheel:
        wheel.writestr(f"{name}/__init__.py", "")
        wheel.writestr(
            f"{info}/WHEEL",
            f"Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: {tag}\n",
        )
        wheel.writestr(f"{info}/METADATA", f"Name: {name}\nVersion: 1.0\n")
        wheel.writestr(f"{info}/RECORD", "")
    return buffer.getvalue()


def test_nothing_is_installed_when_any_wheel_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flask stayed behind when its markupsafe was refused."""
    cache = tmp_path / "cache"

    served = {
        "a-1.0-py3-none-any.whl": wheel_bytes("a", "py3-none-any"),
        "b-1.0-cp315-cp315-ios_13_0_arm64_iphoneos.whl": wheel_bytes(
            "b", "cp315-cp315-ios_13_0_arm64_iphoneos"
        ),
    }

    async def download(client: Any, url: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(served[url.rsplit("/", 1)[1]])

    monkeypatch.setattr(piplike, "download_wheel_async", download)
    a = piplike.Candidate(
        name="a", version=Version("1.0"), link=piplike.Link(PY), identifier="a"
    )
    b = piplike.Candidate(
        name="b", version=Version("1.0"), link=piplike.Link(BIN), identifier="b"
    )
    target = tmp_path / "site"
    target.mkdir()
    with pytest.raises(piplike.DependencyError, match="not pure Python"):
        asyncio.run(piplike.install_resolved({"a": a, "b": b}, target, cache, True))
    assert list(target.iterdir()) == []
