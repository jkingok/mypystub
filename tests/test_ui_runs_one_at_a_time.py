"""One run at a time (#301): a second run is refused while one is in progress.

Runs share the process's streams, input hooks, working directory and the Script
tab, so starting another before the first has ended would mix them up.
"""

from pathlib import Path

import pytest
import toga

from mypystub import ui
from tests.support_ui import run, tap, wait_for


@pytest.fixture
def alerts(proto: ui.Prototype, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Info dialogs shown, by their text."""
    shown: list[str] = []

    async def info(text: str, title: str | None = None) -> None:
        shown.append(text)

    monkeypatch.setattr(proto, "info", info)
    return shown


def write(docs: Path, name: str, source: str) -> None:
    (docs / f"{name}.py").write_text(source)


def ended(proto: ui.Prototype) -> bool:
    return proto.ended_run == proto.run_id and not proto.running


def test_a_second_run_waits_its_turn(
    proto: ui.Prototype, app: toga.App, docs: Path, alerts: list[str], monkeypatch
) -> None:
    write(docs, "asker", "name = input('Name? ')\nprint('Hello', name)\n")
    write(docs, "other", "print('other ran')\n")
    proto.reload_menu(proto.script_list)
    tap(proto, "asker", monkeypatch, app)
    wait_for(app, lambda: proto.input_box.parent is not None)
    assert proto.running

    proto.tabs.current_tab = "List"
    tap(proto, "other", monkeypatch, app)
    assert alerts == ["Another script is already running."]
    assert proto.tabs.current_tab.text == "Script"
    assert "other ran" not in proto.print_text.value

    proto.input_text.value = "Sam"
    proto.input_text.on_confirm()  # type: ignore[misc]  (Toga passes the widget)
    wait_for(app, lambda: ended(proto))
    tap(proto, "other", monkeypatch, app)
    wait_for(app, lambda: ended(proto) and "other ran" in proto.print_text.value)
    assert len(alerts) == 1  # no second alert once the first had ended


def test_a_takeover_counts_until_it_is_popped(
    proto: ui.Prototype, app: toga.App, docs: Path, alerts: list[str], monkeypatch
) -> None:
    write(
        docs,
        "takeover",
        "import toga\n"
        "def show():\n"
        "    window = toga.App.app.main_window\n"
        "    window.content_stack.append((window.title, window.content))\n"
        "    window.content = toga.Box()\n"
        "toga.App.app.loop.call_soon_threadsafe(show)\n",
    )
    write(docs, "other", "print('other ran')\n")
    proto.reload_menu(proto.script_list)
    tap(proto, "takeover", monkeypatch, app)
    window = app.main_window
    wait_for(
        app, lambda: window.content is not proto.tabs and len(window.content_stack)
    )
    assert proto.running
    run(app, proto.run_row(proto_row(proto, "other")))
    assert alerts == ["Another script is already running."]

    window.title, window.content = window.content_stack.pop()
    wait_for(app, lambda: ended(proto))
    tap(proto, "other", monkeypatch, app)
    wait_for(app, lambda: "other ran" in proto.print_text.value)


def proto_row(proto: ui.Prototype, title: str):
    return next(r for r in proto.script_list.data if r.title == title)


def test_a_failure_before_the_run_starts_frees_the_way(
    proto: ui.Prototype, app: toga.App, docs: Path, alerts: list[str], monkeypatch
) -> None:
    """An unexpected error mustn't leave the app unable to run anything."""
    write(docs, "case", "print('ran')\n")
    proto.reload_menu(proto.script_list)

    def broken(row: object) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(proto, "run_settings_for", broken)
    tap(proto, "case", monkeypatch, app)
    assert not proto.running
    monkeypatch.undo()
