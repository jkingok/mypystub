"""Setup's Environment fills the screen and marks inherited rows; Packages folds (#304)."""

from pathlib import Path
from typing import Any

import pytest
import toga

from mypystub import setup_pages, ui


def test_the_environment_list_fills_the_screen(
    proto: ui.Prototype, config: Path
) -> None:
    """No ScrollContainer and no fixed height: the list flexes and scrolls itself."""
    proto.system_env = {f"V{i}": str(i) for i in range(12)}
    form = proto.open_setup_environment()
    assert form.fill
    assert form.env_list.style.flex == 1
    assert form.env_list.style.height in ("none", None)  # no fixed height
    assert not any(
        isinstance(widget, toga.ScrollContainer) for widget in walk(form.content)
    )
    form.done()


def test_a_scripts_form_with_arguments_still_scrolls(
    proto: ui.Prototype, config: Path
) -> None:
    from tests.support_ui import row

    form = proto.open_run_with(row(proto, "top"))
    assert not form.fill
    assert any(isinstance(w, toga.ScrollContainer) for w in walk(form.content))
    form.done()


def test_inherited_rows_carry_the_icon(
    proto: ui.Prototype, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    marker = object()
    monkeypatch.setattr(ui.Prototype, "inherited_icon", property(lambda self: marker))
    proto.system_env = {"TZ": "UTC"}
    proto.settings.set_environment({"MINE": "1"})
    form = proto.open_setup_environment()
    form.show_inherited = True
    form.refresh()
    by_name = {r.title: r for r in form.env_list.data}
    assert by_name["TZ"].icon is marker
    assert by_name["TZ"].subtitle == "UTC"  # the icon says it; the ⓘ gives the source
    assert by_name["MINE"].subtitle == "1"
    form.done()


def test_without_the_icon_file_the_text_says_it(
    proto: ui.Prototype, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ui.Prototype, "inherited_icon", property(lambda self: None))
    proto.system_env = {"TZ": "UTC"}
    form = proto.open_setup_environment()
    assert [r.subtitle for r in form.env_list.data] == ["from the system · UTC"]
    form.done()


def test_user_packages_fold() -> None:
    html = setup_pages.packages_html("2 user packages", {"a": "1", "b": "2"}, None)
    user = html.split("<h3>User packages</h3>")[1].split("<h3>")[0]
    assert "<details><summary>2 packages</summary>" in user
    assert "2 user packages" in user  # the summary stays in view


def walk(widget: Any) -> list[Any]:
    found, pending = [], [widget]
    while pending:
        current = pending.pop()
        found.append(current)
        pending.extend(getattr(current, "children", None) or [])
    return found
