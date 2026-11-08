"""The resume state file: saving, reading it back safely, and finding folders (#188)."""

import json
from pathlib import Path

import pytest

from mypystub import resume

STATE = resume.Resume(
    version="2026.11.8.1",
    tab="Setup",
    category="Documents",
    folder="a/b",
    package="a/pkg",
    setup_page="packages",
    help_page="About",
    running="Documents/a/b/tool.py",
    running_title="tool",
)


def test_state_round_trips(tmp_path: Path) -> None:
    """What is saved is what is loaded, for the same app version."""
    path = resume.state_path(tmp_path)
    assert path == tmp_path / "resume.json"
    assert resume.save(path, STATE)
    assert resume.load(path, "2026.11.8.1") == STATE


def test_nothing_saved_means_nothing_to_resume(tmp_path: Path) -> None:
    """No file, and no error."""
    assert resume.load(tmp_path / "resume.json", "1") is None


def test_another_app_version_is_not_resumed(tmp_path: Path) -> None:
    """The app may behave differently after an update, so start fresh."""
    path = tmp_path / "resume.json"
    resume.save(path, STATE)
    assert resume.load(path, "2026.11.9.1") is None
    assert resume.load(path, "") is None  # no version to compare: don't resume


@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "[]",
        "null",
        '{"schema": 99, "version": "1"}',
        '{"version": "1"}',
        '{"schema": 1, "version": 1}',
        '{"schema": 1, "version": "1", "tab": 3}',
        '{"schema": 1, "version": "1", "folder": null}',
    ],
)
def test_a_bad_file_is_ignored_without_an_error(tmp_path: Path, text: str) -> None:
    """Unreadable, the wrong shape, another schema, or wrong types: no resume."""
    path = tmp_path / "resume.json"
    path.write_text(text)
    assert resume.load(path, "1") is None


def test_unknown_fields_from_a_later_app_are_ignored(tmp_path: Path) -> None:
    """Extra keys don't stop an older reader."""
    path = tmp_path / "resume.json"
    path.write_text(json.dumps({"schema": 1, "version": "1", "tab": "Logs", "x": [1]}))
    state = resume.load(path, "1")
    assert state is not None and state.tab == "Logs"


def test_none_is_allowed_where_the_field_is_optional(tmp_path: Path) -> None:
    """A page that isn't open is null."""
    path = tmp_path / "resume.json"
    resume.save(path, resume.Resume(version="1"))
    raw = json.loads(path.read_text())
    assert raw["setup_page"] is None and raw["schema"] == 1
    assert resume.load(path, "1") == resume.Resume(version="1")


def test_saving_is_atomic_and_leaves_no_temporary_file(tmp_path: Path) -> None:
    """The file is replaced whole."""
    path = tmp_path / "data" / "resume.json"
    assert resume.save(path, STATE) and resume.save(path, resume.Resume(version="1"))
    assert sorted(p.name for p in path.parent.iterdir()) == ["resume.json"]


def test_a_save_that_cannot_happen_returns_false(tmp_path: Path) -> None:
    """A read-only or missing place never raises."""
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert resume.save(blocker / "resume.json", STATE) is False


def test_clear_forgets_and_is_safe_twice(tmp_path: Path) -> None:
    """Removing a missing file is fine."""
    path = tmp_path / "resume.json"
    resume.save(path, STATE)
    resume.clear(path)
    resume.clear(path)
    assert not path.exists()


def test_nearest_existing_walks_up_to_the_first_folder_that_is_there(
    tmp_path: Path,
) -> None:
    """A deleted folder gives its nearest surviving parent, ending at the top."""
    (tmp_path / "a" / "b").mkdir(parents=True)
    (tmp_path / "a" / "file.py").write_text("x")
    assert resume.nearest_existing(tmp_path, "a/b") == "a/b"
    assert resume.nearest_existing(tmp_path, "a/b/c/d") == "a/b"
    assert resume.nearest_existing(tmp_path, "a/gone/deeper") == "a"
    assert (
        resume.nearest_existing(tmp_path, "a/file.py") == "a"
    )  # a file isn't a folder
    assert resume.nearest_existing(tmp_path, "gone") == ""
    assert resume.nearest_existing(tmp_path, "") == ""


def test_a_path_that_leaves_the_category_counts_as_gone(tmp_path: Path) -> None:
    """Nothing outside the category is ever restored."""
    (tmp_path / "base" / "in").mkdir(parents=True)
    (tmp_path / "outside").mkdir()
    assert resume.nearest_existing(tmp_path / "base", "../outside") == ""
    assert resume.nearest_existing(tmp_path / "base", "in/../../outside") == ""
    assert resume.nearest_existing(tmp_path / "base", "/etc") == ""
