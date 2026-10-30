"""Checks that the packaging metadata in pyproject.toml is self-consistent."""

import tomllib
from pathlib import Path

import pytest

PYPROJECT = Path(__file__).parent.parent / "pyproject.toml"

pytestmark = pytest.mark.skipif(
    not PYPROJECT.exists(), reason="pyproject.toml is not bundled on device"
)


def _load() -> dict:
    """Return the parsed pyproject.toml."""
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_briefcase_requires_match_project_dependencies() -> None:
    """The app bundle ships the same packages that the code imports on desktop."""
    config = _load()
    project = set(config["project"]["dependencies"])
    briefcase = set(config["tool"]["briefcase"]["app"]["mypystub"]["requires"])
    assert project == briefcase
