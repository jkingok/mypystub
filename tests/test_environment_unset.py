"""Unset variables saved in launcher.toml and applied to a run (#176)."""

import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from mypystub.run_settings import RunSettings
from mypystub.runner import RunContext, target_for
from mypystub.settings import Settings


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A fresh Settings (it's a singleton) writing to a temp config folder."""
    monkeypatch.setattr(Settings, "_instance", None)
    return Settings(SimpleNamespace(config=tmp_path))  # type: ignore[arg-type]


def test_setup_environment_keeps_unset_names(settings: Settings) -> None:
    """Values in [environment], unset names beside them; a variable may be 'unset'."""
    settings.set_environment({"GREETING": "Hi", "TZ": None, "unset": "yes"})
    assert "environment_unset" in settings.config_file.read_text()
    assert settings.get_environment() == {"GREETING": "Hi", "TZ": None, "unset": "yes"}


def test_clearing_the_unset_names_removes_the_key(settings: Settings) -> None:
    """Nothing unset: nothing written."""
    settings.set_environment({"TZ": None})
    settings.set_environment({"TZ": "UTC"})
    assert "environment_unset" not in settings.config_file.read_text()
    assert settings.get_environment() == {"TZ": "UTC"}


def test_a_scripts_unset_names_are_saved_with_it(settings: Settings) -> None:
    """[run_with."key"] gets an unset list beside env."""
    key = "Documents/tool.py"
    settings.set_run_with(key, RunSettings(["x"], {"A": "1", "TZ": None}))
    assert settings.get_run_with(key) == RunSettings(["x"], {"A": "1", "TZ": None})
    assert 'unset = ["TZ"]' in settings.config_file.read_text()


def test_an_existing_file_without_unset_still_reads(settings: Settings) -> None:
    """Files written before this have no unset keys, and read as before."""
    settings.config_file.write_text(
        '[environment]\nGREETING = "Hi"\n\n[run_with."a.py"]\nargs = ["x"]\n'
        'env = { B = "2" }\n'
    )
    assert settings.get_environment() == {"GREETING": "Hi"}
    assert settings.get_run_with("a.py") == RunSettings(["x"], {"B": "2"})


def test_an_unset_variable_is_gone_for_the_run_and_back_after(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """None removes the variable inside the run; the environment is restored."""
    monkeypatch.setenv("REMOVE_ME", "present")
    monkeypatch.setenv("KEEP_ME", "kept")
    seen = tmp_path / "seen.txt"
    script = tmp_path / "s.py"
    script.write_text(
        "import os\n"
        f"open({str(seen)!r}, 'w').write(repr((os.environ.get('REMOVE_ME'),"
        " os.environ.get('KEEP_ME'), os.environ.get('NEW'))))\n"
    )
    env = {"REMOVE_ME": None, "NEW": "x"}
    with RunContext(target_for(script, tmp_path), env=env) as run:
        run.run()
    assert seen.read_text() == repr((None, "kept", "x"))
    assert os.environ["REMOVE_ME"] == "present" and "NEW" not in os.environ


def test_unsetting_a_variable_that_is_not_set_is_harmless(tmp_path: Path) -> None:
    """No error for a name that isn't there."""
    script = tmp_path / "s.py"
    script.write_text("pass\n")
    with RunContext(target_for(script, tmp_path), env={"NOT_THERE_XYZ": None}) as run:
        run.run()
