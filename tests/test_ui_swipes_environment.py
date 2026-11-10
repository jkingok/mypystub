"""The system's variables in Setup, unsetting, and hiding inherited ones (#176).

Skipped where toga_dummy isn't installed, such as on device.
"""

import os
from pathlib import Path
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import press, row, run, select


def rows(form: Any) -> list[tuple[str, str]]:
    """The environment list as (name, subtitle)."""
    return [(r.title, r.subtitle) for r in form.env_list.data]


def show_inherited(form: Any, shown: bool = True) -> None:
    """Flip the switch as the user would."""
    form.inherited_switch.value = shown
    form._toggle_inherited(form.inherited_switch)


def test_inherited_variables_start_hidden_with_a_count(
    proto: ui.Prototype, config: Path
) -> None:
    """The system's variables alone would fill the screen, so they are off."""
    proto.system_env = {"TZ": "UTC", "HOME": "/home/me"}
    form = proto.open_setup_environment()
    assert rows(form) == []
    assert form.inherited_switch is not None
    assert form.inherited_switch.text == "Show inherited variables (2 hidden)"
    # The switch says how many are hidden, and the section how many are listed
    assert form.sections["env"][0].text == "Environment (0)"
    form.done()


def test_the_switch_lists_them_with_where_they_come_from_first(
    proto: ui.Prototype, config: Path
) -> None:
    """The origin leads the line, since a long value is cut off."""
    proto.system_env = {"TZ": "UTC", "HOME": "/home/me"}
    form = proto.open_setup_environment()
    show_inherited(form)
    assert rows(form) == [
        ("HOME", "from the system · /home/me"),
        ("TZ", "from the system · UTC"),
    ]
    assert form.inherited_switch.text == "Show inherited variables"
    show_inherited(form, False)
    assert rows(form) == []
    form.done()


def test_the_choice_is_shared_by_every_setup_screen(
    proto: ui.Prototype, config: Path
) -> None:
    """Switch it on once, and the next form opens with them shown."""
    proto.system_env = {"TZ": "UTC"}
    first = proto.open_setup_environment()
    show_inherited(first)
    first.done()
    assert proto.show_inherited_env is True
    second = proto.open_run_with(row(proto, "top"))
    assert rows(second) == [("TZ", "from the system · UTC")]
    assert second.inherited_switch is not None and second.inherited_switch.value
    second.done()


def test_overriding_loses_the_marker_and_deleting_brings_it_back(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """Edit to override; delete the override to restore the system's value."""
    proto.system_env = {"TZ": "UTC"}
    form = proto.open_setup_environment()
    show_inherited(form)
    select(form.env_list, form._env_selected, 0)
    run(app, form.set_env("TZ", "Europe/London", form.selected_env()))
    assert rows(form) == [("TZ", "Europe/London")]
    assert proto.settings.get_environment() == {"TZ": "Europe/London"}
    press(app, form.env_buttons["delete"])
    assert rows(form) == [("TZ", "from the system · UTC")]
    assert proto.settings.get_environment() == {}
    form.done()


def test_an_override_shows_even_when_inherited_ones_are_hidden(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """What this layer sets is always visible: it is the point of the screen."""
    proto.system_env = {"TZ": "UTC", "HOME": "/h"}
    form = proto.open_setup_environment()
    show_inherited(form)
    select(form.env_list, form._env_selected, 1)  # TZ
    run(app, form.set_env("TZ", "Europe/London", form.selected_env()))
    show_inherited(form, False)
    assert rows(form) == [("TZ", "Europe/London")]
    assert form.inherited_switch.text == "Show inherited variables (1 hidden)"
    form.done()


def test_a_system_variable_can_be_overridden_to_blank(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """Blank is a value, so it overrides; it is not the same as unset."""
    proto.system_env = {"TZ": "UTC"}
    form = proto.open_setup_environment()
    show_inherited(form)
    select(form.env_list, form._env_selected, 0)
    run(app, form.set_env("TZ", "", form.selected_env()))
    assert rows(form) == [("TZ", "(empty)")]
    assert proto.settings.get_environment() == {"TZ": ""}
    form.done()


def test_unset_marks_the_variable_and_is_saved(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """The unset button saves the name as unset, and delete undoes it."""
    proto.system_env = {"TZ": "UTC"}
    form = proto.open_setup_environment()
    show_inherited(form)
    select(form.env_list, form._env_selected, 0)
    assert form.env_buttons["unset"].enabled
    press(app, form.env_buttons["unset"])
    assert rows(form) == [("TZ", "(unset)")]
    assert not form.env_buttons["unset"].enabled  # already unset
    assert proto.settings.get_environment() == {"TZ": None}
    assert "unset here" in form.env_note.text
    press(app, form.env_buttons["delete"])
    assert rows(form) == [("TZ", "from the system · UTC")]
    form.done()


def test_the_note_for_a_system_variable_explains_the_choices(
    proto: ui.Prototype, config: Path
) -> None:
    """Edit (even to blank) or unset; there is no 'change it in the system'."""
    proto.system_env = {"TZ": "UTC"}
    form = proto.open_setup_environment()
    show_inherited(form)
    select(form.env_list, form._env_selected, 0)
    assert "comes from the system" in form.env_note.text
    assert "⊘" in form.env_note.text and "in the system" not in form.env_note.text
    form.done()


def test_view_shows_a_long_value_in_full(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """A PATH is cut off in the row; the dialog has all of it and where it's from."""
    long_path = ":".join(f"/usr/local/some/long/folder/{i}" for i in range(40))
    proto.system_env = {"PATH": long_path}
    told: list[tuple[str, str]] = []

    async def tell(title: str, text: str) -> None:
        told.append((title, text))

    form = proto.open_setup_environment()
    form.tell = tell  # the form keeps the dialog it was opened with
    show_inherited(form)
    assert not form.env_buttons["view"].enabled  # nothing selected
    select(form.env_list, form._env_selected, 0)
    assert form.env_buttons["view"].enabled
    press(app, form.env_buttons["view"])
    assert told == [("PATH", f"From the system.\n\n{long_path}")]
    form.done()


def test_view_says_where_a_value_is_from_and_shows_an_unset(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """Own values say "Set here"; an unset says so."""
    proto.system_env = {"TZ": "UTC"}
    proto.settings.set_environment({"A": "1"})
    told: list[tuple[str, str]] = []

    async def tell(title: str, text: str) -> None:
        told.append((title, text))

    form = proto.open_setup_environment()
    form.tell = tell
    select(form.env_list, form._env_selected, 0)  # A, set here (visible by default)
    press(app, form.env_buttons["view"])
    show_inherited(form)
    select(form.env_list, form._env_selected, 1)  # TZ
    press(app, form.env_buttons["unset"])
    press(app, form.env_buttons["view"])
    assert told[0] == ("A", "Set here.\n\n1")
    assert told[1][0] == "TZ" and told[1][1].startswith("Set here.")
    assert "(unset" in told[1][1]
    form.done()


def test_a_script_sees_the_system_and_setup_layers_and_can_unset_either(
    proto: ui.Prototype, app: toga.App, config: Path
) -> None:
    """Both outer layers are inherited; the script's own Setup can unset them."""
    proto.system_env = {"TZ": "UTC"}
    proto.settings.set_environment({"GREETING": "Hi"})
    form = proto.open_run_with(row(proto, "top"))
    assert rows(form) == []
    show_inherited(form)
    assert rows(form) == [
        ("GREETING", "from Setup · Hi"),
        ("TZ", "from the system · UTC"),
    ]
    select(form.env_list, form._env_selected, 0)
    press(app, form.env_buttons["unset"])
    assert rows(form)[0] == ("GREETING", "(unset)")
    saved = proto.settings.get_run_with("Documents/top.py")
    assert saved.env == {"GREETING": None}
    form.done()


def test_a_run_gets_unset_but_not_the_system_layer(
    proto: ui.Prototype, config: Path
) -> None:
    """The system's variables are already there: only changes are passed on."""
    proto.system_env = {"TZ": "UTC", "HOME": "/h"}
    proto.settings.set_environment({"GREETING": "Hi", "TZ": None})
    own, env = proto.run_settings_for(row(proto, "top"))
    assert env == {"GREETING": "Hi", "TZ": None}  # no HOME, no system TZ value
    assert own.env == {}


def test_the_launcher_remembers_the_environment_it_started_with(
    proto: ui.Prototype,
) -> None:
    """Taken once at the start, so a run changing os.environ can't alter the list."""
    assert isinstance(proto.system_env, dict)
    assert all(isinstance(v, str) for v in proto.system_env.values())


@pytest.mark.parametrize("unset", [False, True])
def test_the_note_is_broken_to_fit_a_small_phone(
    proto: ui.Prototype, app: toga.App, config: Path, unset: bool
) -> None:
    """Labels don't wrap on iOS, so each line of a note must fit an iPhone SE."""
    proto.system_env = {"DYLD_FALLBACK_FRAMEWORK_PATH": "/private/var/run"}
    form = proto.open_setup_environment()
    show_inherited(form)
    select(form.env_list, form._env_selected, 0)
    if unset:
        press(app, form.env_buttons["unset"])
    assert "DYLD_FALLBACK_FRAMEWORK_PATH" in form.env_note.text
    assert max(len(line) for line in form.env_note.text.splitlines()) <= 40
    form.done()
