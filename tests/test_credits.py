"""Checks that every bundled icon is credited in CREDITS.md."""

from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CREDITS = ROOT / "CREDITS.md"
ICONS = ROOT / "src" / "mypystub" / "resources" / "icons"

pytestmark = pytest.mark.skipif(
    not CREDITS.exists(), reason="CREDITS.md is not bundled on device"
)


def test_every_icon_is_credited() -> None:
    """Each PNG in resources/icons appears in CREDITS.md."""
    credits = CREDITS.read_text(encoding="utf-8")
    icons = sorted(p.name for p in ICONS.glob("*.png"))
    assert icons, "no icons found; has the resources folder moved?"
    missing = [name for name in icons if f"`{name}`" not in credits]
    assert not missing, f"add these icons to CREDITS.md: {missing}"


def test_help_page_credits_flaticon() -> None:
    """The in-app Help page carries the attribution too."""
    help_md = ROOT / "src" / "mypystub" / "resources" / "templates" / "help.md"
    assert "Uicons by Flaticon" in help_md.read_text(encoding="utf-8")
