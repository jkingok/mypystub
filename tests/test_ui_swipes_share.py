"""Share on the Setup form of a script, project, zipapp or package (#147).

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import share_items, ui, ui_swipe
from tests.support_ui import press, row, run


@pytest.fixture
def shared(monkeypatch: pytest.MonkeyPatch) -> list[Path]:
    """Pretend to be on iOS, and record what reaches the share sheet."""
    sent: list[Path] = []
    monkeypatch.setattr(share_items, "share_available", lambda: True)
    monkeypatch.setattr(ui_swipe, "open_share_sheet", lambda w, path: sent.append(path))
    return sent


def project_row(folder: Path) -> SimpleNamespace:
    """A project row for `folder`."""
    folder.mkdir()
    (folder / "pyproject.toml").write_text("[project]\nname='p'\n")
    return SimpleNamespace(
        kind="project", title="p", project_dir=str(folder), dependencies=[]
    )


def test_a_script_form_offers_share_and_shares_the_file(
    proto: ui.Prototype, app: toga.App, docs: Path, shared: list[Path]
) -> None:
    """The file itself goes to the share sheet."""
    form = proto.open_run_with(row(proto, "top"))
    assert form.share_button is not None
    press(app, form.share_button)
    assert shared == [docs / "top.py"]
    form.done()


def test_a_project_form_shares_a_zip_that_pastes_back(
    proto: ui.Prototype, app: toga.App, docs: Path, shared: list[Path]
) -> None:
    """A folder is zipped under its own name."""
    form = proto.open_run_with(project_row(docs / "tool"))
    assert form.share_button is not None
    press(app, form.share_button)
    assert len(shared) == 1 and shared[0].name == "tool.zip"
    with zipfile.ZipFile(shared[0]) as zf:
        assert zf.namelist() == ["tool/pyproject.toml"]
    form.done()


def test_a_package_of_entry_points_shares_its_project(
    proto: ui.Prototype, app: toga.App, docs: Path, shared: list[Path]
) -> None:
    """A package row, which cannot run, still shares its project."""
    package = project_row(docs / "pkg")
    package.kind = "package"
    form = proto.open_run_with(package)
    assert form.share_button is not None
    press(app, form.share_button)
    assert shared[0].name == "pkg.zip"
    form.done()


def test_off_ios_there_is_no_share_button(
    proto: ui.Prototype, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The share sheet is iOS only, so the button is left out."""
    monkeypatch.setattr(share_items, "share_available", lambda: False)
    form = proto.open_run_with(row(proto, "top"))
    assert form.share_button is None and form.on_share is None
    form.done()


def test_a_vanished_file_is_reported_not_shared(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    shared: list[Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the file has gone since the list was drawn, the user is told."""
    shown: list[str] = []

    async def error(text: str, title: str | None = None) -> None:
        shown.append(text)

    monkeypatch.setattr(proto, "error", error)
    target = row(proto, "top")
    (docs / "top.py").unlink()
    run(app, proto.share_row(target))
    assert shared == [] and shown and "top.py" in shown[0]


def labels(widget: toga.Widget) -> list[str]:
    """The text of every label under `widget`."""
    found = [widget.text] if isinstance(widget, toga.Label) else []
    for child in widget.children:
        found += labels(child)
    return found


def test_the_share_note_is_broken_to_fit_a_small_phone(
    proto: ui.Prototype, shared: list[Path]
) -> None:
    """Labels don't wrap on iOS, so each line must fit an iPhone SE by itself."""
    form = proto.open_run_with(row(proto, "top"))
    (note,) = [text for text in labels(form.content) if text.startswith("Share")]
    assert max(len(line) for line in note.splitlines()) <= 40
    form.done()
