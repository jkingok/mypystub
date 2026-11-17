"""List row icons are Icons where the platform needs them (Windows, Linux).

Skipped where toga_dummy isn't installed, such as on device.
"""

from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import ui
from tests.support_ui import ICONS

PNG = ICONS / "folder.png"


def row_icons(proto: ui.Prototype) -> list[object]:
    return [r.icon for r in proto.script_list.data if r.icon is not None]


@pytest.mark.parametrize("platform", ["win32", "linux"])
def test_desktop_lists_get_icons(
    proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    """Winforms needs an Icon's path; an Image has none."""
    monkeypatch.setattr(ui.sys, "platform", platform)
    if not PNG.exists():
        pytest.skip("icon files not added")
    proto.reload_menu(proto.script_list)
    icons = row_icons(proto)
    assert icons and all(isinstance(i, toga.Icon) for i in icons)


@pytest.mark.parametrize("platform", ["android", "darwin"])
def test_apple_and_android_keep_images(
    proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch, platform: str
) -> None:
    """iOS, Android and macOS take an Image, which is what lets iOS tint them."""
    monkeypatch.setattr(ui.sys, "platform", platform)
    assert isinstance(proto.list_icon(PNG), toga.Image)


def test_a_prototypes_own_icon_is_an_icon_in_the_row_and_an_image_as_splash(
    proto: ui.Prototype, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ui.sys, "platform", "win32")
    (docs / "pic.png").write_bytes(PNG.read_bytes())
    (docs / "iconic.py").write_text(
        "# /// script\n# [tool.stub_launcher]\n# icon = 'pic.png'\n# ///\n"
    )
    proto.reload_menu(proto.script_list)
    (row,) = [r for r in proto.script_list.data if r.title == "iconic"]
    assert isinstance(row.icon, toga.Icon)
    assert isinstance(row.splash, toga.Image)
