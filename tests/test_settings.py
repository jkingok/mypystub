"""Tests for the launcher settings file (launcher.toml)."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from mypystub.settings import CONFIG_NAME, Settings


@pytest.fixture
def settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """A fresh Settings (it's a singleton) writing to a temp config folder."""
    monkeypatch.setattr(Settings, "_instance", None)
    return Settings(SimpleNamespace(config=tmp_path))  # type: ignore[arg-type]


def test_get_table_missing_is_empty(settings: Settings) -> None:
    """An optional table that isn't in the file reads as {}."""
    assert settings.get_table("aliases") == {}


def test_get_table_reads_aliases(settings: Settings) -> None:
    """[aliases] comes back as plain dicts, ready for parse_aliases."""
    path = settings.config_path / CONFIG_NAME
    path.write_text(
        path.read_text()
        + '\n[aliases]\nfast = { kind = "substitute", target = "fast-pure" }\n'
    )
    assert settings.get_table("aliases") == {
        "fast": {"kind": "substitute", "target": "fast-pure"}
    }


def test_run_with_settings_round_trip(settings: Settings) -> None:
    """Saved arguments and variables come back, under their path's key."""
    from mypystub.run_settings import RunSettings

    key = "Examples/basics/show_args.py"
    assert settings.get_run_with(key) == RunSettings()
    settings.set_run_with(key, RunSettings(["--name", "Ada"], {"B": "2", "A": "1"}))
    settings.set_run_with("Documents/tools:greet", RunSettings(["x"]))
    assert settings.get_run_with(key) == RunSettings(
        ["--name", "Ada"], {"A": "1", "B": "2"}
    )
    text = settings.config_file.read_text()
    assert '[run_with."Examples/basics/show_args.py"]' in text
    assert '[run_with."Documents/tools:greet"]' in text
    # The defaults file's comments survive
    assert "# Package aliases" in text


def test_environment_only_settings(settings: Settings) -> None:
    """Things without their own arguments save only variables."""
    from mypystub.run_settings import RunSettings

    settings.set_run_with(
        "Documents/pkg", RunSettings(["ignored"], {"A": "1"}), with_args=False
    )
    assert settings.get_run_with("Documents/pkg") == RunSettings([], {"A": "1"})


def test_setup_environment(settings: Settings) -> None:
    """Setup's variables are saved in [environment], alphabetised."""
    assert settings.get_environment() == {}
    settings.set_environment({"b": "2", "A": "1"})
    assert settings.get_environment() == {"A": "1", "b": "2"}
    assert "[environment]" in settings.config_file.read_text()


def test_hand_edited_unusable_variables_are_ignored(settings: Settings) -> None:
    """Bad names or values typed into launcher.toml never reach a run."""
    path = settings.config_path / CONFIG_NAME
    path.write_text(
        path.read_text()
        + '\n[environment]\nOK = "1"\n"MY VAR" = "2"\n"A=B" = "3"\nNUL = "a\\u0000b"\n'
        + '\n[run_with."Documents/a.py"]\nargs = []\n'
        + 'env = { GOOD = "1", "bad-name" = "2" }\n'
    )
    assert settings.get_environment() == {"OK": "1"}
    assert settings.get_run_with("Documents/a.py").env == {"GOOD": "1"}
