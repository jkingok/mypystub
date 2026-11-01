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
