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


def test_python_version_is_four_numbers() -> None:
    """The build number is a fourth release number: 1.2.3.4, no words."""
    version = load().python_version("2026.11.2", 3)
    assert version == "2026.11.2.3"
    parsed = Version(version)
    assert str(parsed) == version  # already in normal form
    assert parsed.release == (2026, 11, 2, 3)
    assert (parsed.pre, parsed.post, parsed.dev, parsed.local) == (None,) * 4


def test_versions_order_and_match_xcode() -> None:
    """Builds and days increase; the first three numbers are Xcode's version."""
    sv = load()
    first, second, tenth, next_day = (
        Version(sv.python_version(day, n))
        for day, n in (
            ("2026.11.2", 1),
            ("2026.11.2", 2),
            ("2026.11.2", 10),
            ("2026.11.3", 1),
        )
    )
    assert first < second < tenth < next_day
    xcode_version = ".".join(map(str, tenth.release[:3]))
    assert xcode_version == "2026.11.2"  # CFBundleShortVersionString
    assert tenth.release[3] == 10  # CFBundleVersion


@pytest.mark.parametrize("calver", ["2026.11.02", "2026.01.2", "26.11.2", "2026.11"])
def test_rejects_calver_that_is_not_pep440_normal(calver: str) -> None:
    """Leading zeros would differ between Xcode and Python metadata."""
    with pytest.raises(ValueError, match="calver"):
        load().python_version(calver, 1)


@pytest.mark.parametrize("build", [0, -1])
def test_rejects_build_below_one(build: int) -> None:
    """Build numbers start at 1: the lane takes TestFlight's latest plus one."""
    with pytest.raises(ValueError, match="build"):
        load().python_version("2026.11.2", build)


def test_stamp_sets_versions_and_build_keeping_comments() -> None:
    """Both versions and Briefcase's build are set; the file's comments survive."""
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    stamped = load().stamp(text, "2026.11.2.3", 3)
    doc = tomlkit.parse(stamped)
    assert doc["project"]["version"] == "2026.11.2.3"
    assert doc["tool"]["briefcase"]["version"] == "2026.11.2.3"
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
            '+ version = "2026.11.2.3"',
            '+ version = "2026.11.2.3"',
            "+ build = 3",
        ]
    )


def test_main_writes_the_file(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The command line stamps a pyproject.toml and prints the Python version."""
    target = tmp_path / "pyproject.toml"
    target.write_text((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    load().main(["2026.11.2", "4", "--pyproject", str(target)])
    assert tomlkit.parse(target.read_text())["project"]["version"] == "2026.11.2.4"
    assert capsys.readouterr().out.strip() == "2026.11.2.4"
