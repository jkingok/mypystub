"""Setup remembers the last update check: shown on opening, asked once a day."""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import git_updates, maintenance, piplike, release_check, ui
from tests.support_ui import run


@pytest.fixture
def asked(
    proto: ui.Prototype, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> list[str]:
    """PyPI and python.org stand-ins, recording what is asked."""
    record: list[str] = []
    proto.cache_path = tmp_path / "cache"
    monkeypatch.setattr(piplike, "get_package_inventory", lambda site: {"rich": "14.0"})
    monkeypatch.setattr(piplike, "get_bundled_inventory", lambda site: {})
    monkeypatch.setattr(release_check, "check_build", lambda client, version: None)
    monkeypatch.setattr(git_updates, "bundled_from_git", lambda inventory: {})

    def python(client: Any, current: str) -> maintenance.PythonStatus:
        record.append("python.org")
        v = maintenance.Version(current)
        return maintenance.PythonStatus(v, v, None, None)

    def latest(client: Any, name: str) -> maintenance.Version:
        record.append(name)
        return maintenance.Version("14.1")

    monkeypatch.setattr(maintenance, "check_python", python)
    monkeypatch.setattr(maintenance, "latest_on_pypi", latest)
    return record


def test_checking_again_today_asks_nothing_new(
    proto: ui.Prototype, app: toga.App, asked: list[str]
) -> None:
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))
    assert asked == ["rich", "python.org"]
    assert "Last checked" in proto.setup_html
    run(app, proto.handle_check_updates(proto.update_all_button))
    assert asked == ["rich", "python.org"]  # all from today's answers
    assert "14.0 → 14.1" in proto.setup_html


def test_the_page_opens_with_the_last_results(
    proto: ui.Prototype, app: toga.App, asked: list[str]
) -> None:
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))
    proto.close_setup_page()
    # As after a restart: nothing checked in this session
    proto.last_checked = None
    proto.checked_updates = None
    proto.health = None
    asked.clear()
    proto.open_setup_page("packages")
    assert asked == []  # shown without asking anyone
    assert "14.0 → 14.1" in proto.setup_html and "Last checked" in proto.setup_html
    assert proto.update_all_button.enabled


def test_never_checked_shows_no_date(
    proto: ui.Prototype, app: toga.App, asked: list[str]
) -> None:
    proto.open_setup_page("packages")
    assert "Last checked" not in proto.setup_html
