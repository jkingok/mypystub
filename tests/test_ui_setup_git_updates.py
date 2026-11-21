"""Setup's app health compares packages bundled from git with their branch (#328)."""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import git_updates, maintenance, piplike, release_check, setup_pages, ui
from tests.support_ui import run

OLD, NEW = "a" * 40, "b" * 40


def test_git_packages_are_compared_with_their_branch_not_pypi(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proto.cache_path = tmp_path / "cache"
    bundled = {"toga-console": "0.1.dev26", "certifi": "2026.1.1"}
    console = git_updates.GitSource(
        "toga-console", "https://github.com/beeware/toga-console", OLD
    )
    monkeypatch.setattr(piplike, "get_package_inventory", lambda site: {})
    monkeypatch.setattr(piplike, "get_bundled_inventory", lambda site: bundled)
    monkeypatch.setattr(release_check, "check_build", lambda client, version: None)
    monkeypatch.setattr(maintenance, "check_python", lambda client, current: None)
    monkeypatch.setattr(
        git_updates, "bundled_from_git", lambda inventory: {"toga-console": console}
    )
    asked_pypi: list[str] = []

    def find_updates(client: Any, inventory: Any, **kwargs: Any) -> list[Any]:
        asked_pypi.extend(inventory)
        return []

    monkeypatch.setattr(maintenance, "find_updates", find_updates)
    monkeypatch.setattr(git_updates, "latest_commit", lambda client, source: NEW)
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))

    assert asked_pypi == ["certifi"]  # toga-console isn't compared with PyPI
    health = proto.health
    assert health is not None and [u.name for u in health.git_updates] == [
        "toga-console"
    ]
    assert health.count == 1
    assert "toga-console: newer commits on the default branch" in proto.setup_html
    assert (
        f"https://github.com/beeware/toga-console/compare/{OLD}...{NEW}"
        in proto.setup_html
    )


def test_the_health_section_links_to_each_comparison() -> None:
    update = git_updates.GitUpdate("x", OLD, NEW, "main", "https://example.com/c")
    html = setup_pages.health_section(maintenance.Health(None, [], None, [update]))
    assert '<a href="https://example.com/c">x</a>' in html
    assert "x: newer commits on main" in html
