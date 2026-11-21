"""Arguments show no subtitle and the Environment shows only the value (#337)."""

from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")

from mypystub import ui
from tests.support_ui import row
from togax_jkingok import lists


def test_arguments_are_a_title_each_in_shorter_rows(
    proto: ui.Prototype, config: Path
) -> None:
    form = proto.open_run_with(row(proto, "top"))
    form.args += ["--name", "Ada"]
    form.changed()
    assert [r.title for r in form.args_list.data] == ["--name", "Ada"]
    assert all(getattr(r, "subtitle", None) in (None, "") for r in form.args_list.data)
    assert form.args_list.style.height == 2 * lists.ONE_LINE_ROW_HEIGHT
    assert lists.ONE_LINE_ROW_HEIGHT < lists.ROW_HEIGHT
    form.done()


def test_an_inherited_row_gives_the_value_and_the_source_is_in_the_details(
    proto: ui.Prototype, config: Path
) -> None:
    proto.system_env = {"TZ": "UTC"}
    form = proto.open_setup_environment()
    form.show_inherited = True
    form.refresh()
    inherited = {r.title: r for r in form.env_list.data}["TZ"]
    assert inherited.subtitle == "UTC"
    assert getattr(inherited, "icon", None) is not None  # the icon marks it
    # The ⓘ dialog says where it comes from, with the full value
    told: list[tuple[str, str]] = []

    async def tell(title: str, text: str) -> None:
        told.append((title, text))

    form.tell = tell
    form.env_name = "TZ"
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(form.view_env())
    finally:
        loop.close()
    assert told == [("TZ", "From the system.\n\nUTC")]
    form.done()
