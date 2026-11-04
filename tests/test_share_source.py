"""Sharing the app's own Python source, as a backstop to the About Source link.

The zip helper is plain logic. The About-page button wiring uses the launcher
fixtures and is skipped where toga_dummy isn't installed.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from zipfile import ZipFile

from mypystub.ui_helpers import create_source_zip


def test_source_zip_holds_the_package_and_skips_pycache(tmp_path: Path) -> None:
    """The zip is this package's folder, named with the version, without caches."""
    app = SimpleNamespace(
        formal_name="MyPyStub",
        version="9.9",
        paths=SimpleNamespace(cache=tmp_path / "cache"),
    )
    archive = create_source_zip(app)  # type: ignore[arg-type]
    assert archive.name == "mypystub-9.9-source.zip"
    with ZipFile(archive) as zf:
        names = zf.namelist()
    assert "mypystub/ui.py" in names
    assert "mypystub/ui_helpers.py" in names
    assert not any("__pycache__" in name for name in names)


# -- About-page button (dummy backend) --------------------------------------


def test_source_button_zips_and_shares(proto, monkeypatch) -> None:
    """The About button zips the source and hands it to the share sheet."""
    import mypystub.ui as ui_mod

    shared: dict = {}
    monkeypatch.setattr(ui_mod, "create_source_zip", lambda app: Path("/tmp/x.zip"))
    monkeypatch.setattr(
        ui_mod, "open_share_sheet", lambda w, path: shared.setdefault("path", path)
    )
    proto.handle_source_share(proto.source_share)
    assert shared["path"] == Path("/tmp/x.zip")


def test_source_button_follows_the_share_button(proto) -> None:
    """It shows exactly when the Share button does: only on the About page."""
    proto.help_selection.selection.value = "About"
    proto.show_help_page()
    assert proto.source_share.style.visibility == proto.about_share.style.visibility
    proto.help_selection.selection.value = "Help"
    proto.show_help_page()
    assert proto.source_share.style.visibility == "hidden"
