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


# Every declared permission must be used, or App Review rejects the build. Each
# one maps to a bundled example and a marker showing that it uses the hardware.
EXAMPLES = PYPROJECT.parent / "src" / "mypystub" / "resources" / "examples"
PERMISSION_USES = {
    "fine_location": ("hardware/where_am_i.py", "location.current_location"),
    "camera": ("hardware/take_photo.py", "camera.take_photo"),
    "photo_library": ("hardware/take_photo.py", "UIImageWriteToSavedPhotosAlbum"),
}
INFO_USES = {
    "NSLocalNetworkUsageDescription": ("hardware/router_check.py", "create_connection"),
}


def _app() -> dict:
    """The Briefcase app table."""
    return _load()["tool"]["briefcase"]["app"]["mypystub"]


def test_declared_permissions_match_the_examples() -> None:
    """Exactly the permissions with an example are declared (#63)."""
    assert set(_app().get("permission", {})) == set(PERMISSION_USES)


def test_ios_usage_descriptions_match_the_examples() -> None:
    """Exactly the iOS-only usage descriptions with an example are declared."""
    info = _app()["iOS"]["info"]
    declared = {key for key in info if key.endswith("UsageDescription")}
    assert declared == set(INFO_USES)


@pytest.mark.parametrize(
    ("key", "example", "marker"),
    [(k, *v) for k, v in {**PERMISSION_USES, **INFO_USES}.items()],
)
def test_each_permission_is_used_by_an_example(
    key: str, example: str, marker: str
) -> None:
    """App Review needs every permission we ask for to be used somewhere."""
    source = (EXAMPLES / example).read_text(encoding="utf-8")
    assert marker in source, f"{example} should use {key} ({marker})"
