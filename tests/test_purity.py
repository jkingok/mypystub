"""Only pure Python is installed at run time (#172)."""

import zipfile
from pathlib import Path

import pytest

from mypystub import purity


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
