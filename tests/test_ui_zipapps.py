"""UI tests for zipapps in the list.

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import (
    row,
    run,
    tap,
    titles,
    wait_for,
)

# Zipapps (#124)
# ---------------------------------------------------------------------------


def write_pyz(path: Path, *, entries: bool = False) -> None:
    """Write a small zipapp: a __main__ that prints, and optional entry points."""
    import zipfile

    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("__main__.py", "import sys\nprint('main', sys.argv[1:])\n")
        archive.writestr("zt/__init__.py", "")
        archive.writestr(
            "zt/cli.py",
            "import sys\n\ndef one():\n    print('one', sys.argv)\n\n"
            "def two():\n    print('two')\n",
        )
        archive.writestr(
            "zt-1.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: zt\nVersion: 1\nSummary: Zipped tools\n",
        )
        if entries:
            archive.writestr(
                "zt-1.dist-info/entry_points.txt",
                "[console_scripts]\none = zt.cli:one\ntwo = zt.cli:two\n",
            )


def test_zipapp_row_runs_with_saved_arguments(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A .pyz is listed, its settings are keyed by its path, and a tap runs it."""
    from mypystub.run_settings import RunSettings

    write_pyz(docs / "zt.pyz")
    proto.reload_menu(proto.script_list)
    assert (
        row(proto, "zt").kind == "zipapp"
        and row(proto, "zt").subtitle == "Zipped tools"
    )
    proto.settings.set_run_with("Documents/zt.pyz", RunSettings(["--go"], {}))
    tap(proto, "zt", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.print_text.value == "main ['--go']\n"


def test_zipapp_with_entry_points_opens_like_a_package(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Several entry points: a folder of rows, each run with its own settings."""
    from mypystub.run_settings import RunSettings

    write_pyz(docs / "zt.pyz", entries=True)
    proto.reload_menu(proto.script_list)
    assert row(proto, "zt").kind == "package"
    tap(proto, "zt", monkeypatch, app)
    assert titles(proto) == ["..", "one", "two"]
    proto.settings.set_run_with("Documents/zt.pyz:one", RunSettings(["x"], {}))
    tap(proto, "one", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.print_text.value == "one ['one', 'x']\n"


def test_zipapp_info_page(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    messages: list[tuple],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Info on a zipapp, and on one of its entries, opens its page."""
    write_pyz(docs / "zt.pyz", entries=True)
    proto.reload_menu(proto.script_list)
    run(app, proto.show_info(row(proto, "zt")))
    assert "Zipped tools" in proto.readme_page and "Entry points" in proto.readme_page
    proto.pop_screen()
    tap(proto, "zt", monkeypatch, app)
    run(app, proto.show_info(row(proto, "one")))
    assert "An entry point of zt" in proto.readme_page
    proto.pop_screen()


def test_broken_zipapp_fails_when_run(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No scanning for problems: the error appears when it runs."""
    (docs / "bad.pyz").write_bytes(b"not a zip")
    proto.reload_menu(proto.script_list)
    assert row(proto, "bad").kind == "zipapp"
    tap(proto, "bad", monkeypatch, app)
    wait_for(app, lambda: bool(proto.dialogs))  # type: ignore[attr-defined]
    assert proto.dialogs[-1][0] == "Script Failure"  # type: ignore[attr-defined]
