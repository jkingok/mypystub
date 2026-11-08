"""Fixtures for the launcher's UI tests, on Toga's dummy backend (#53, #140).

Only the launcher itself lives here (the app, a folder of scripts, a launcher
opened on it). Fixtures one feature uses stay with that feature's tests; the
helper functions are in tests/support_ui.py.

Nothing here imports Toga at module level: where toga_dummy isn't installed,
such as on device, only the tests that ask for these fixtures are skipped.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    import toga

    from mypystub import ui


@pytest.fixture(scope="session")
def app() -> toga.App:
    """One dummy app for the whole run; Toga expects a single App per process."""
    import toga

    from tests import support_ui  # noqa: F401 (selects the dummy backend)

    app = toga.App("UI test", "org.example.uitest", startup=lambda app: toga.Box())
    app.main_window = toga.MainWindow()
    return app


@pytest.fixture
def docs(tmp_path: Path) -> Path:
    """A User documents folder with nested scripts."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "b" / "deep.py").write_text('"""Deep down."""\n')
    (tmp_path / "top.py").write_text('"""At the top."""\n')
    return tmp_path


@pytest.fixture
def proto(app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch) -> ui.Prototype:
    """A launcher opened on Documents, with dialogs recorded instead of shown."""
    from mypystub import ui
    from tests.support_ui import fresh_stack, tap

    monkeypatch.setattr(app, "user_documents_dir", docs, raising=False)
    p = ui.Prototype(host_app=app, on_done=lambda _: None)
    p.system_env = {}  # not this machine's environment, which tests mustn't see
    fresh_stack(p)
    app.main_window.content = p.get_content()
    p.dialogs = []  # type: ignore[attr-defined]

    async def record(text: str, title: str | None = None) -> None:
        p.dialogs.append(  # type: ignore[attr-defined]
            (title, text, p.tabs.current_tab.text, p.script_activity.text.text)
        )

    monkeypatch.setattr(p, "error", record)
    # On iOS, clear_selection deselects the row once it has been read; do the
    # same on the dummy backend, or every list reload re-fires on_select.
    monkeypatch.setattr(
        p, "clear_selection", lambda widget: widget._impl._set_value("selection", None)
    )
    p.reload_menu(p.script_list)
    tap(p, "Documents", monkeypatch, app)
    return p


@pytest.fixture
def config(
    proto: ui.Prototype, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Point the launcher's settings at a fresh launcher.toml for this test."""
    settings = proto.settings
    path = tmp_path / "launcher.toml"
    shutil.copy(settings.config_defaults, path)
    monkeypatch.setattr(settings, "config_file", path)
    settings.config_doc = settings._load()
    return path


@pytest.fixture
def messages(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> list[tuple]:
    """Info dialogs and yes/no questions, recorded instead of shown."""
    shown: list[tuple] = []

    async def info(text: str, title: str | None = None) -> None:
        shown.append((title, text))

    monkeypatch.setattr(proto, "info", info)
    return shown
