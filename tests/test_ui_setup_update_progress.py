"""Check for updates and Update all count their steps on Setup's progress bar."""

from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import git_updates, maintenance, piplike, release_check, ui
from tests.support_ui import run


def fake_find_updates(client: Any, inventory: Any, **kwargs: Any) -> list[Any]:
    """Report every package as checked, and find nothing."""
    for name in sorted(inventory):
        if kwargs.get("on_check"):
            kwargs["on_check"](name)
    return []


def test_check_for_updates_counts_every_request(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proto.cache_path = tmp_path / "cache"
    user = {"humanize": "4.10.0", "rich": "14.0"}
    bundled = {"toga-core": "0.5", "certifi": "2026.1.1", "httpx2": "1.0"}
    monkeypatch.setattr(piplike, "get_package_inventory", lambda site: user)
    monkeypatch.setattr(piplike, "get_bundled_inventory", lambda site: bundled)
    monkeypatch.setattr(release_check, "check_build", lambda client, version: None)
    monkeypatch.setattr(maintenance, "check_python", lambda client, current: None)
    monkeypatch.setattr(maintenance, "find_updates", fake_find_updates)
    monkeypatch.setattr(git_updates, "bundled_from_git", lambda inventory: {})
    counts: list[tuple[int, int]] = []
    texts: list[str] = []
    count, update = proto.setup_activity.count, proto.setup_activity.update

    def record_count(done: int, total: int) -> None:
        counts.append((done, total))
        count(done, total)

    def record_text(value: str = "", on: bool = True) -> None:
        texts.append(value)
        update(value, on)

    monkeypatch.setattr(proto.setup_activity, "count", record_count)
    monkeypatch.setattr(proto.setup_activity, "update", record_text)
    proto.open_setup_page("packages")
    run(app, proto.handle_check_updates(proto.update_all_button))

    total = len(user) + len(bundled) + 2  # GitHub Releases and python.org
    assert counts == [(done, total) for done in range(total)]
    assert "🔍 humanize" in texts
    assert "🔍 GitHub Releases" in texts
    assert "🔍 python.org" in texts
    assert "🔍 toga-core" in texts
    assert not proto.setup_activity.counting  # gone once the check is done


def test_update_all_passes_the_count_to_the_installer(
    proto: ui.Prototype, app: toga.App, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from packaging.version import Version

    proto.cache_path = tmp_path / "cache"
    proto.pending_updates = [
        maintenance.Update("humanize", Version("4.10.0"), Version("4.12.0"), False)
    ]
    seen: dict[str, Any] = {}

    async def install(requirements: list[str], target: Path, **kwargs: Any) -> None:
        seen.update(kwargs)
        kwargs["on_count"](1, 2)
        seen["counting"] = proto.setup_activity.counting

    monkeypatch.setattr(piplike, "resolve_and_install_async", install)
    proto.open_setup_page("packages")
    run(app, proto.handle_update_all(proto.update_all_button))
    assert seen["counting"]
    assert not proto.setup_activity.counting
