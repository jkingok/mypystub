"""Tests for scripts/set_version.py, which stamps release versions (#61)."""

import difflib
import importlib.util
from pathlib import Path

import pytest
import tomlkit
from packaging.version import Version

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "set_version.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not bundled on device"
)


def load():
    """Import the script as a module."""
    spec = importlib.util.spec_from_file_location("set_version", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("kind", "expected"),
    [("release", "2026.11.2.post3"), ("dev", "2026.11.2.dev3")],
)
def test_python_version(kind: str, expected: str) -> None:
    """TestFlight builds are .postN, device/dev builds .devN (PEP 440)."""
    version = load().python_version("2026.11.2", 3, kind)
    assert version == expected
    assert str(Version(version)) == version  # already in normal form


def test_versions_order_and_match_xcode() -> None:
    """Builds increase, and the base version is exactly Xcode's marketing version."""
    sv = load()
    dev, post1, post2 = (
        Version(sv.python_version("2026.11.2", n, k))
        for n, k in ((3, "dev"), (1, "release"), (2, "release"))
    )
    assert dev < Version("2026.11.2") < post1 < post2
    assert post2.base_version == "2026.11.2"  # CFBundleShortVersionString
    assert post2.post == 2  # CFBundleVersion


@pytest.mark.parametrize("calver", ["2026.11.02", "2026.01.2", "26.11.2", "2026.11"])
def test_rejects_calver_that_is_not_pep440_normal(calver: str) -> None:
    """Leading zeros would differ between Xcode and Python metadata."""
    with pytest.raises(ValueError, match="calver"):
        load().python_version(calver, 1, "release")


@pytest.mark.parametrize(("build", "kind"), [(0, "release"), (-1, "dev"), (1, "beta")])
def test_rejects_bad_build_or_kind(build: int, kind: str) -> None:
    """Release builds start at 1; the kind is release or dev."""
    with pytest.raises(ValueError):
        load().python_version("2026.11.2", build, kind)


def test_stamp_sets_versions_and_build_keeping_comments() -> None:
    """Both versions and Briefcase's build are set; the file's comments survive."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    stamped = load().stamp(text, "2026.11.2.post3", 3)
    doc = tomlkit.parse(stamped)
    assert doc["project"]["version"] == "2026.11.2.post3"
    assert doc["tool"]["briefcase"]["version"] == "2026.11.2.post3"
    assert doc["tool"]["briefcase"]["build"] == 3
    assert "# Version is managed by Fastlane" in stamped
    # Nothing else changes: two versions replaced, one build line added
    current = tomlkit.parse(text)["project"]["version"]
    diff = [
        line
        for line in difflib.ndiff(text.splitlines(), stamped.splitlines())
        if line[:2] in ("+ ", "- ")
    ]
    assert sorted(diff) == sorted(
        [
            f'- version = "{current}"',
            f'- version = "{current}"',
            '+ version = "2026.11.2.post3"',
            '+ version = "2026.11.2.post3"',
            "+ build = 3",
        ]
    )


def test_main_writes_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command line stamps a pyproject.toml and prints the Python version."""
    target = tmp_path / "pyproject.toml"
    target.write_text((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    load().main(["2026.11.2", "4", "dev", "--pyproject", str(target)])
    assert tomlkit.parse(target.read_text())["project"]["version"] == "2026.11.2.dev4"
    assert capsys.readouterr().out.strip() == "2026.11.2.dev4"
