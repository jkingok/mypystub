"""The system Back button on each screen (ui_back.BackMixin).

Skipped where toga_dummy isn't installed, such as on device.
"""

from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")

import toga

from mypystub import ui
from tests.support_ui import fresh_stack, row, run, tap, titles


def showing(app: toga.App) -> object:
    return app.main_window.content


def show(proto: ui.Prototype, app: toga.App, tab: str) -> None:
    """Switch tabs as a tap does, and let the switch settle and be recorded."""
    proto.tabs.current_tab = tab
    proto.refresh_tab(proto.tabs)


def test_back_retraces_the_tabs_in_the_order_they_were_shown(
    proto: ui.Prototype, app: toga.App
) -> None:
    proto.tab_history.clear()
    proto.show_category(None)  # the categories: the list has nothing to climb
    for tab in ("List", "Logs", "Help", "Setup"):
        show(proto, app, tab)
    for expected in ("Help", "Logs", "List"):
        assert proto.handle_back() is True
        proto.refresh_tab(proto.tabs)  # the switch Back made is recorded too
        assert proto.tabs.current_tab.text == expected
    assert proto.handle_back() is False  # the first tab: Android leaves


def test_a_tab_shown_twice_in_a_row_counts_once(proto: ui.Prototype) -> None:
    proto.tab_history.clear()
    for tab in ("List", "Logs", "Logs"):
        proto.note_tab(tab)
    assert proto.tab_history == ["List", "Logs"]


def test_the_history_is_kept_short(proto: ui.Prototype) -> None:
    proto.tab_history.clear()
    for n in range(proto.TAB_HISTORY + 5):
        proto.note_tab("List" if n % 2 else "Logs")
    assert len(proto.tab_history) == proto.TAB_HISTORY


def test_back_climbs_the_list_then_lets_android_leave(
    proto: ui.Prototype, app: toga.App, docs: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The proto fixture has Documents open; a/b is a folder two levels down."""
    tap(proto, "a", monkeypatch, app)
    tap(proto, "b", monkeypatch, app)
    assert proto.subfolder == Path("a/b")
    assert proto.handle_back() and proto.subfolder == Path("a")
    assert proto.handle_back() and proto.subfolder == Path()
    assert proto.handle_back() and proto.category is None  # the categories
    assert "Documents" in titles(proto)
    proto.tab_history[:] = ["List"]
    assert proto.handle_back() is False  # nowhere further: Android leaves


def test_back_leaves_an_open_package(proto: ui.Prototype) -> None:
    proto.package_dir = Path("somewhere")
    assert proto.handle_back() is True
    assert proto.package_dir is None


def test_a_pushed_screen_uses_its_own_back(proto: ui.Prototype, app: toga.App) -> None:
    pressed: list[str] = []

    def own_back() -> None:
        pressed.append("own")
        proto.pop_screen()

    proto.push_screen("Page", toga.Box(), on_back=own_back)
    assert proto.handle_back() is True
    assert pressed == ["own"] and showing(app) is proto.tabs
    assert proto.back_actions == []


def test_a_screen_without_its_own_back_is_popped(
    proto: ui.Prototype, app: toga.App
) -> None:
    proto.push_screen("Info", toga.Box())
    assert proto.handle_back() is True
    assert showing(app) is proto.tabs


def test_info_screen(proto: ui.Prototype, app: toga.App) -> None:
    proto.show_page("Info", "<p>hello</p>")
    assert proto.handle_back() and showing(app) is proto.tabs


def test_setup_page_closes_and_forgets_the_page(
    proto: ui.Prototype, app: toga.App
) -> None:
    proto.open_setup_page(next(iter(proto.SETUP_PAGES)))
    assert proto.handle_back() and showing(app) is proto.tabs
    assert proto.setup_page is None


def test_a_rows_setup_form_is_done(proto: ui.Prototype, app: toga.App) -> None:
    proto.open_run_with(row(proto, "top"))
    assert showing(app) is not proto.tabs
    assert proto.handle_back() and showing(app) is proto.tabs


def test_the_import_preview_is_cancelled(proto: ui.Prototype, app: toga.App) -> None:
    proto._pending_import = ("text", "print(1)", Path())
    proto.show_import_preview("Paste", "<p>x</p>")
    assert proto.handle_back() and showing(app) is proto.tabs
    assert proto._pending_import is None


def test_the_fallback_text_prompt_is_cancelled(
    proto: ui.Prototype, app: toga.App
) -> None:
    from mypystub import prompts

    async def ask_then_back() -> list[str] | None:
        pending = app.loop.create_task(
            proto.ask_fields_screen("Name", "", [prompts.Field("Name", "x")])
        )
        await __import__("asyncio").sleep(0)
        assert proto.handle_back() is True
        return await pending

    assert run(app, ask_then_back()) is None
    assert showing(app) is proto.tabs


def test_a_prototypes_takeover_is_left_to_android(
    proto: ui.Prototype, app: toga.App
) -> None:
    """The prototype's own Back may save or confirm; we don't pop it for it."""
    fresh_stack(proto)
    stack = proto.content_stack()
    mw = app.main_window
    stack.floor = len(stack)  # what a run sets
    stack.append((mw.title, mw.content))
    takeover = toga.Box()
    mw.content = takeover  # the prototype's own screen
    assert proto.handle_back() is False
    assert showing(app) is takeover and len(stack) == stack.floor + 1
