"""A folder's Setup: the same page as a category's, inherited by what's in it (#348, #349).

Skipped where toga_dummy isn't installed, such as on device.
"""

from pathlib import Path

import pytest

pytest.importorskip("toga_dummy")

from mypystub import ui
from mypystub.run_settings import RunSettings
from tests.support_ui import row

DEEP = "Documents/a/b/deep.py"


def deep_row(proto: ui.Prototype) -> object:
    """The script a/b/deep.py, rebuilt from its settings key."""
    found = proto.row_for_key(DEEP)
    assert found is not None
    return found


def test_a_folder_page_is_the_category_page_with_the_inherited_icon(
    proto: ui.Prototype, config: Path
) -> None:
    folder = proto.open_folder_setup(row(proto, "a"))
    assert folder.title == "a" and folder.with_args is False
    assert folder.inherited_icon is not None  # #349
    category = proto.open_category_setup("Documents")
    assert category.inherited_icon is not None  # #349: both pages
    folder.done()
    category.done()


def test_a_folder_s_variables_reach_the_scripts_inside_it(
    proto: ui.Prototype, config: Path
) -> None:
    proto.settings.set_run_with("Documents", RunSettings([], {"WHO": "category"}))
    proto.settings.set_run_with("Documents/a", RunSettings([], {"WHO": "folder"}))
    _, merged = proto.run_settings_for(deep_row(proto))
    assert merged["WHO"] == "folder"  # the folder beats the category


def test_the_folder_page_inherits_from_its_parents(
    proto: ui.Prototype, config: Path
) -> None:
    proto.settings.set_run_with("Documents/a", RunSettings([], {"WHO": "outer"}))
    layers = proto.inherited_layers(row(proto, "a"))
    assert "Documents" in [layer.source for layer in layers]
    assert "a" not in [layer.source for layer in layers]  # not its own folder


def test_a_scripts_own_variables_beat_its_folders(
    proto: ui.Prototype, config: Path
) -> None:
    proto.settings.set_run_with("Documents/a", RunSettings([], {"WHO": "folder"}))
    deep = deep_row(proto)
    proto.settings.set_run_with(proto.row_key(deep), RunSettings(["x"], {"WHO": "own"}))
    _, merged = proto.run_settings_for(deep)
    assert merged["WHO"] == "own"


def test_the_innermost_folder_wins_over_its_parent(
    proto: ui.Prototype, config: Path
) -> None:
    proto.settings.set_run_with("Documents/a", RunSettings([], {"WHO": "outer"}))
    proto.settings.set_run_with("Documents/a/b", RunSettings([], {"WHO": "inner"}))
    _, merged = proto.run_settings_for(deep_row(proto))
    assert merged["WHO"] == "inner"


def test_a_folders_working_folder_is_inherited_innermost_first(
    proto: ui.Prototype, config: Path
) -> None:
    proto.settings.set_run_with("Documents/a", RunSettings([], {}, "documents:outer"))
    deep = deep_row(proto)
    assert proto.inherited_workdir(deep) == ("documents:outer", "a")
    proto.settings.set_run_with("Documents/a/b", RunSettings([], {}, "documents:inner"))
    assert proto.inherited_workdir(deep) == ("documents:inner", "b")
