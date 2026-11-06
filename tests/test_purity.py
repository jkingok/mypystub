"""Only pure Python is installed at run time (#172)."""

import tomllib
import zipfile
from pathlib import Path
from typing import Any

import pytest

from mypystub import purity
from tests.support_sources import TOGA_CONSOLE_LIKE, write_tree


def wheel(
    tmp_path: Path, name: str = "foo-1.0-py3-none-any.whl", **members: str
) -> Path:
    """A wheel file holding `members` (path -> text), plus a WHEEL file."""
    path = tmp_path / name
    files = {
        "foo-1.0.dist-info/WHEEL": "Wheel-Version: 1.0\nRoot-Is-Purelib: true\n",
        "foo.py": "x = 1\n",
    }
    files.update({k.replace("__", "/"): v for k, v in members.items()})
    with zipfile.ZipFile(path, "w") as archive:
        for member, content in files.items():
            archive.writestr(member, content)
    return path


def test_a_pure_wheel_passes(tmp_path: Path) -> None:
    """py3-none-any, Root-Is-Purelib true, only Python files."""
    assert purity.wheel_impurity(wheel(tmp_path)) is None


@pytest.mark.parametrize(
    "name",
    [
        "foo-1.0-cp315-cp315-ios_13_0_arm64_iphoneos.whl",
        "foo-1.0-cp315-cp315-macosx_11_0_arm64.whl",
        "foo-1.0-py3-none-macosx_11_0_arm64.whl",
        "foo-1.0-cp315-abi3-any.whl",
    ],
)
def test_platform_tags_mean_impure(tmp_path: Path, name: str) -> None:
    """A wheel built for a platform or ABI is not pure."""
    assert "not pure Python" in (purity.wheel_impurity(wheel(tmp_path, name)) or "")


def test_root_is_purelib_false_is_impure(tmp_path: Path) -> None:
    """A wheel that says so itself, even when tagged any."""
    path = wheel(tmp_path, **{"foo-1.0.dist-info__WHEEL": "Root-Is-Purelib: false\n"})
    assert "Root-Is-Purelib" in (purity.wheel_impurity(path) or "")


@pytest.mark.parametrize("member", ["foo/_speed.so", "foo/lib.dylib", "foo/x.pyd"])
def test_a_binary_inside_a_pure_looking_wheel_is_impure(
    tmp_path: Path, member: str
) -> None:
    """Tagged any, but carrying compiled code."""
    path = wheel(tmp_path, **{member.replace("/", "__"): "binary"})
    assert "compiled code" in (purity.wheel_impurity(path) or "")


def project(tmp_path: Path, **changes: Any) -> tuple[Path, dict[str, Any], list[Path]]:
    """A toga-console-like tree, with `changes` applied (path -> text or None)."""
    files = dict(TOGA_CONSOLE_LIKE)
    for key, value in changes.items():
        key = key.replace("__", "/")
        if value is None:
            files.pop(key, None)
        else:
            files[key] = value
    root = write_tree(tmp_path, files)
    data = tomllib.loads((root / "pyproject.toml").read_text())
    return root, data, [root / "src" / "toga_console"]


def test_a_plain_setuptools_project_is_fine(tmp_path: Path) -> None:
    """A pure project with a pure backend needs nothing but copying."""
    assert purity.tree_impurity(*project(tmp_path)) is None


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (
            {
                "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"].replace(
                    "setuptools.build_meta", "maturin"
                )
            },
            "compiles code",
        ),
        (
            {
                "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"].replace(
                    "setuptools.build_meta", "somebackend.api"
                )
            },
            "isn't run here",
        ),
        (
            {
                "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"].replace(
                    '"setuptools_scm==10.3.4"', '"cython"'
                )
            },
            "cython",
        ),
        (
            {
                "pyproject.toml": TOGA_CONSOLE_LIKE["pyproject.toml"]
                + "\n[[tool.setuptools.ext-modules]]\nname='x'\nsources=['x.c']\n"
            },
            "extension modules",
        ),
        (
            {"setup.py": "from setuptools import Extension\next_modules=[]\n"},
            "setup.py",
        ),
        ({"Cargo.toml": "[package]\n"}, "Cargo.toml"),
        ({"src__toga_console__fast.pyx": "cdef int x\n"}, "fast.pyx"),
        ({"src__toga_console__lib.so": "binary"}, "lib.so"),
    ],
)
def test_anything_that_needs_a_build_is_refused(
    tmp_path: Path, change: dict[str, str], fragment: str
) -> None:
    """Compiled backends, build requirements, extensions and compiled files."""
    reason = purity.tree_impurity(*project(tmp_path, **change))
    assert reason is not None and fragment in reason
