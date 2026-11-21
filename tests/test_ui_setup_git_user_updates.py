"""User packages installed from git: checked on their branch, updated from it."""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import git_updates, maintenance, piplike, release_check, ui
from tests.support_ui import run

OLD, NEW = "a" * 40, "b" * 40


def test_a_git_package_behind_its_branch_is_listed_and_updated(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proto.cache_path = tmp_path / "cache"
    thing = git_updates.GitSource("thing", "https://github.com/o/thing", OLD, "dev")
    monkeypatch.setattr(
        piplike, "get_package_inventory", lambda site: {"thing": "1.0", "rich": "14"}
    )
    monkeypatch.setattr(piplike, "get_bundled_inventory", lambda site: {})
    monkeypatch.setattr(git_updates, "git_sources", lambda paths=None: {"thing": thing})
    monkeypatch.setattr(git_updates, "bundled_from_git", lambda inventory: {})
    monkeypatch.setattr(git_updates, "latest_commit", lambda client, source: NEW)
    monkeypatch.setattr(release_check, "check_build", lambda client, version: None)
    monkeypatch.setattr(maintenance, "check_python", lambda client, current: None)
    asked_pypi: list[str] = []

    def find_updates(client: Any, inventory: Any, **kwargs: Any) -> list[Any]:
        asked_pypi.extend(inventory)
        return []

    monkeypatch.setattr(maintenance, "find_updates", find_updates)
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))

    assert "thing" not in asked_pypi and "rich" in asked_pypi
    assert "aaaaaaa → bbbbbbb on dev" in proto.setup_html
    assert f"https://github.com/o/thing/compare/{OLD}...{NEW}" in proto.setup_html
    assert proto.update_all_button.enabled

    installed: list[list[str]] = []

    async def install(requirements: list[str], target: Path, **kwargs: Any) -> None:
        installed.append(requirements)

    monkeypatch.setattr(piplike, "resolve_and_install_async", install)
    run(app, proto.handle_update_all(proto.update_all_button))
    assert installed == [["thing @ git+https://github.com/o/thing@dev"]]
    assert proto.git_user_updates == [] and not proto.update_all_button.enabled
