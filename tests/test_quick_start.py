"""Quick Start: the prototype offered to run at launch.

The parsing and naming helpers are plain logic and run everywhere. The rest
use the dummy-backend launcher fixtures and are skipped where toga_dummy isn't
installed, such as on device.
"""

from __future__ import annotations

from pathlib import Path, PurePath

import pytest

from mypystub.run_settings import parse_settings_key, quick_start_name, settings_key


@pytest.mark.parametrize(
    "category, relative, entry",
    [
        ("Documents", PurePath("top.py"), None),
        ("Documents", PurePath("a/b/deep.py"), None),
        ("Documents", PurePath("proj"), "run"),
        ("Examples", PurePath(), None),
    ],
)
def test_parse_round_trips_settings_key(
    category: str, relative: PurePath, entry: str | None
) -> None:
    """parse_settings_key is the inverse of settings_key."""
    assert parse_settings_key(settings_key(category, relative, entry)) == (
        category,
        relative,
        entry,
    )


def test_parse_rejects_empty_or_category_less() -> None:
    """A key must name a category."""
    assert parse_settings_key("") is None
    assert parse_settings_key("/no/category") is None


def test_quick_start_name_is_a_short_label() -> None:
    """The name drops the category and shows an entry point after a dot."""
    assert quick_start_name("Documents/games/pong.py") == "games/pong.py"
    assert quick_start_name("Documents/proj:run") == "proj · run"
    assert quick_start_name("Examples") == "Examples"


# -- Launcher behaviour (dummy backend) -------------------------------------


def test_settings_quick_start_round_trip(proto, config) -> None:
    """The key is saved to and cleared from launcher.toml."""
    s = proto.settings
    assert s.get_quick_start() is None
    s.set_quick_start("Documents/top.py")
    assert s.get_quick_start() == "Documents/top.py"
    assert "quick_start" in config.read_text()
    s.set_quick_start(None)
    assert s.get_quick_start() is None


def test_resolve_finds_the_script(proto, config) -> None:
    """A saved key resolves to its runnable row."""
    proto.settings.set_quick_start("Documents/top.py")
    row = proto.resolve_quick_start()
    assert row is not None
    assert row.title == "top"


def test_resolve_clears_a_missing_target(proto, config) -> None:
    """A deleted target is dropped so it can't block launch."""
    proto.settings.set_quick_start("Documents/gone.py")
    assert proto.resolve_quick_start() is None
    assert proto.settings.get_quick_start() is None


def test_resolve_rejects_a_folder(proto, config) -> None:
    """A plain folder isn't runnable, so it isn't a Quick Start."""
    proto.settings.set_quick_start("Documents/a")
    assert proto.resolve_quick_start() is None
    assert proto.settings.get_quick_start() is None


def test_offer_runs_on_yes(proto, config, app, monkeypatch) -> None:
    """Saying yes at launch runs the resolved row."""
    from tests.support_ui import run

    proto.settings.set_quick_start("Documents/top.py")
    ran: list = []

    async def ask(title: str, text: str) -> bool:
        return True

    async def run_row(row) -> None:
        ran.append(row)

    monkeypatch.setattr(proto, "ask", ask)
    monkeypatch.setattr(proto, "run_row", run_row)
    run(app, proto.offer_quick_start())
    assert len(ran) == 1
    assert ran[0].title == "top"


def test_offer_skips_on_no(proto, config, app, monkeypatch) -> None:
    """Saying no runs nothing."""
    from tests.support_ui import run

    proto.settings.set_quick_start("Documents/top.py")
    ran: list = []

    async def ask(title: str, text: str) -> bool:
        return False

    async def run_row(row) -> None:
        ran.append(row)

    monkeypatch.setattr(proto, "ask", ask)
    monkeypatch.setattr(proto, "run_row", run_row)
    run(app, proto.offer_quick_start())
    assert ran == []


def test_make_quick_start_sets_then_replaces(proto, config, app, monkeypatch) -> None:
    """The first choice saves silently; a different one asks before replacing."""
    from tests.support_ui import run

    asked: list = []

    async def ask(title: str, text: str) -> bool:
        asked.append(text)
        return True

    async def info(text: str, title: str | None = None) -> None:
        pass

    monkeypatch.setattr(proto, "ask", ask)
    monkeypatch.setattr(proto, "info", info)

    assert run(app, proto.make_quick_start("Documents/top.py", "top")) is True
    assert proto.settings.get_quick_start() == "Documents/top.py"
    assert asked == []  # nothing to replace, so no question

    # The same row again is a no-op and asks nothing
    assert run(app, proto.make_quick_start("Documents/top.py", "top")) is True
    assert asked == []

    # A different row asks, then replaces
    assert run(app, proto.make_quick_start("Documents/a/b/deep.py", "deep")) is True
    assert len(asked) == 1
    assert proto.settings.get_quick_start() == "Documents/a/b/deep.py"


def test_make_quick_start_keeps_current_on_decline(
    proto, config, app, monkeypatch
) -> None:
    """Declining the replacement leaves the current Quick Start in place."""
    from tests.support_ui import run

    proto.settings.set_quick_start("Documents/top.py")

    async def ask(title: str, text: str) -> bool:
        return False

    async def info(text: str, title: str | None = None) -> None:
        pass

    monkeypatch.setattr(proto, "ask", ask)
    monkeypatch.setattr(proto, "info", info)
    assert run(app, proto.make_quick_start("Documents/a/b/deep.py", "deep")) is False
    assert proto.settings.get_quick_start() == "Documents/top.py"


def offer(proto, app, monkeypatch, answer: bool) -> dict:
    """Offer a Quick Start in a subfolder, answering `answer`; returns what happened."""
    from tests.support_ui import run

    seen: dict = {"asked": [], "ran": []}

    async def ask(title: str, text: str) -> bool:
        seen["asked"].append(text)
        return answer

    async def run_row(row) -> None:
        seen["ran"].append((row, proto.category, proto.subfolder))

    monkeypatch.setattr(proto, "ask", ask)
    monkeypatch.setattr(proto, "run_row", run_row)
    proto.settings.set_quick_start("Documents/a/inner.py")
    run(app, proto.offer_quick_start())
    return seen


def test_saying_no_leaves_the_list_where_it_is(
    proto, config, app, docs, monkeypatch
) -> None:
    """Without this, the next list reload jumped into the Quick Start's folder."""
    (docs / "a" / "inner.py").write_text("print('hi')\n")
    proto.show_category(None)
    seen = offer(proto, app, monkeypatch, False)
    assert seen["ran"] == []
    assert proto.category is None
    assert proto.subfolder == Path()


def test_a_bad_target_leaves_the_list_where_it_is(proto, config) -> None:
    """Checking a Quick Start never moves the list, even when it fails."""
    proto.show_category(None)
    proto.settings.set_quick_start("Documents/a")
    assert proto.resolve_quick_start() is None
    assert proto.category is None


def test_saying_yes_opens_its_folder_and_names_its_path(
    proto, config, app, docs, monkeypatch
) -> None:
    """The prompt tells same-named scripts apart, and the list follows the run."""
    (docs / "a" / "inner.py").write_text("print('hi')\n")
    proto.show_category(None)
    seen = offer(proto, app, monkeypatch, True)
    assert seen["asked"] == ["Do you want to run a/inner.py?"]
    assert [place[1:] for place in seen["ran"]] == [("Documents", Path("a"))]
