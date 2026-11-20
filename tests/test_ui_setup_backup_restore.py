"""Setup's Backup (on a worker thread) and Restore buttons (#303)."""

import json
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest
import toga

from mypystub import backups, ui, ui_setup
from tests.support_ui import run


def test_backup_runs_off_the_main_thread_and_shares_the_zip(
    proto: ui.Prototype, app: toga.App, monkeypatch: pytest.MonkeyPatch
) -> None:
    threads: list[threading.Thread] = []
    real = backups.create

    def create(*args: Any, **kwargs: Any) -> Path:
        threads.append(threading.current_thread())
        return real(*args, **kwargs)

    shared: list[Path] = []
    monkeypatch.setattr(backups, "create", create)
    monkeypatch.setattr(ui_setup, "open_share_sheet", lambda w, p: shared.append(p))
    button = toga.Button("Backup")
    run(app, proto.handle_backup_press(button))
    assert threads and threads[0] is not threading.main_thread()
    assert shared and zipfile.is_zipfile(shared[0])
    assert button.enabled and button.text == "Backup"


def backup_zip(tmp_path: Path) -> Path:
    archive = tmp_path / "b.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr(
            "manifest.json",
            json.dumps(
                {"format": backups.FORMAT, "version": 1, "documents": ["hello.py"]}
            ),
        )
        zf.writestr("documents/hello.py", "print('restored')\n")
    return archive


def test_restore_accepts_only_a_backup(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch
) -> None:
    from mypystub import bridge

    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("x.py", "")

    async def pasteboard(into: Path) -> tuple[str, str]:
        return ("file", str(plain))

    monkeypatch.setattr(bridge, "read_pasteboard", pasteboard, raising=False)
    run(app, proto.handle_restore_press(toga.Button("Restore")))
    assert proto.dialogs[-1][0] == "Not a backup"  # type: ignore[attr-defined]
    assert proto._pending_restore is None


def test_restore_previews_then_restores(
    proto: ui.Prototype, app: toga.App, docs: Path, tmp_path: Path, monkeypatch
) -> None:
    from mypystub import bridge

    archive = backup_zip(tmp_path)

    async def pasteboard(into: Path) -> tuple[str, str]:
        return ("file", str(archive))

    told: list[str] = []

    async def info(text: str, title: str | None = None) -> None:
        told.append(text)

    monkeypatch.setattr(bridge, "read_pasteboard", pasteboard, raising=False)
    monkeypatch.setattr(proto, "info", info)
    run(app, proto.handle_restore_press(toga.Button("Restore")))
    assert proto._pending_restore is not None
    assert app.main_window.content is not proto.tabs  # the preview screen is up
    run(app, proto.confirm_restore())
    assert (docs / "hello.py").read_text() == "print('restored')\n"
    assert told and "Added hello.py" in told[-1]


def test_nothing_on_the_clipboard_says_how(
    proto: ui.Prototype, app: toga.App, monkeypatch
) -> None:
    from mypystub import bridge

    async def pasteboard(into: Path) -> None:
        return None

    told: list[str] = []

    async def info(text: str, title: str | None = None) -> None:
        told.append(title or "")

    monkeypatch.setattr(bridge, "read_pasteboard", pasteboard, raising=False)
    monkeypatch.setattr(proto, "info", info)
    run(app, proto.handle_restore_press(toga.Button("Restore")))
    assert told == ["Nothing to restore"]
