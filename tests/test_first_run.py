"""Which tab the app opens on, from the version last run (#125)."""

from pathlib import Path

import pytest

from mypystub import first_run
from mypystub.first_run import StartState


def test_no_record_is_a_new_user(tmp_path: Path) -> None:
    """Nothing stored means this is the first run."""
    assert first_run.start_state(tmp_path, "2026.11.3.1") is StartState.NEW


def test_matching_version_is_a_returning_user(tmp_path: Path) -> None:
    """The same version as last time opens as usual."""
    first_run.record_version(tmp_path, "2026.11.3.1")
    assert first_run.start_state(tmp_path, "2026.11.3.1") is StartState.SAME


def test_different_version_is_an_update(tmp_path: Path) -> None:
    """A different stored version means the app was updated."""
    first_run.record_version(tmp_path, "2026.11.2.3")
    assert first_run.start_state(tmp_path, "2026.11.3.1") is StartState.UPDATED


def test_record_overwrites_and_makes_the_folder(tmp_path: Path) -> None:
    """Recording replaces the old value, creating the cache folder if needed."""
    cache = tmp_path / "cache" / "mypystub"
    assert first_run.record_version(cache, "1") is True
    assert first_run.record_version(cache, "2") is True
    assert first_run.start_state(cache, "2") is StartState.SAME


@pytest.mark.parametrize("version", [None, ""])
def test_unknown_running_version_changes_nothing(
    tmp_path: Path, version: str | None
) -> None:
    """Without a version to compare, behave like a returning user."""
    assert first_run.start_state(tmp_path, version) is StartState.SAME
    assert first_run.record_version(tmp_path, version) is False
    assert not list(tmp_path.iterdir())


def test_unreadable_record_is_not_a_new_user(tmp_path: Path) -> None:
    """If the file can't be read as text, don't treat the user as new."""
    (tmp_path / first_run.RECORD).write_bytes(b"\xff\xfe\x00")
    assert first_run.start_state(tmp_path, "1") is StartState.UPDATED


def test_unwritable_cache_is_ignored(tmp_path: Path) -> None:
    """A cache folder that can't be written to never raises."""
    blocker = tmp_path / "file"
    blocker.write_text("not a folder")
    assert first_run.record_version(blocker / "cache", "1") is False
    assert first_run.start_state(blocker / "cache", "1") is StartState.NEW
