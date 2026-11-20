"""Backup and Restore: Documents and settings in one zip, never the cache (#303)."""

import json
import zipfile
from datetime import datetime
from pathlib import Path

import pytest

from mypystub import backups


@pytest.fixture
def home(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Documents, config and cache folders with some content."""
    documents, config, cache = (tmp_path / n for n in ("docs", "config", "cache"))
    (documents / "proj" / "src").mkdir(parents=True)
    (documents / "tool.py").write_text("print(1)\n")
    (documents / "proj" / "src" / "app.py").write_text("x = 1\n")
    (documents / "backups").mkdir()
    (documents / "backups" / "tool.2026-01-01T000000.py").write_text("old\n")
    (documents / "proj" / "__pycache__").mkdir()
    (documents / "proj" / "__pycache__" / "a.pyc").write_bytes(b"x")
    (documents / ".hidden").write_text("no")
    config.mkdir()
    (config / "launcher.toml").write_text("resume = true\n")
    (config / "resume.json").write_text("{}")
    (cache / "site_packages").mkdir(parents=True)
    (cache / "site_packages" / "big.py").write_text("x" * 1000)
    return documents, config, cache


def make(home: tuple[Path, Path, Path], out: Path) -> Path:
    documents, config, _ = home
    when = datetime(2026, 11, 19, 12, 0, 0)
    return backups.create(documents, config, out, "MyPyStub", "2026.11.19.1", when)


def test_the_zip_holds_documents_and_settings_only(
    home: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    archive = make(home, tmp_path / "out")
    assert archive.name == "mypystub-backup-20261119-120000.zip"
    names = set(zipfile.ZipFile(archive).namelist())
    assert names == {
        "manifest.json",
        "documents/tool.py",
        "documents/proj/src/app.py",
        "config/launcher.toml",
    }
    manifest = json.loads(zipfile.ZipFile(archive).read("manifest.json"))
    assert manifest["format"] == backups.FORMAT and manifest["app_version"] == (
        "2026.11.19.1"
    )
    assert manifest["documents"] == ["proj", "tool.py"]


def test_only_backups_are_accepted(tmp_path: Path) -> None:
    plain = tmp_path / "plain.zip"
    with zipfile.ZipFile(plain, "w") as zf:
        zf.writestr("tool.py", "print(1)\n")
    with pytest.raises(backups.BackupProblem, match="no manifest.json"):
        backups.read_manifest(plain)
    other = tmp_path / "other.zip"
    with zipfile.ZipFile(other, "w") as zf:
        zf.writestr("manifest.json", json.dumps({"format": "something-else"}))
    with pytest.raises(backups.BackupProblem, match="isn't a MyPyStub backup"):
        backups.read_manifest(other)
    text = tmp_path / "notes.txt"
    text.write_text("hi")
    with pytest.raises(backups.BackupProblem, match="isn't a zip"):
        backups.read_manifest(text)


def test_unsafe_paths_are_refused(tmp_path: Path) -> None:
    evil = tmp_path / "evil.zip"
    with zipfile.ZipFile(evil, "w") as zf:
        zf.writestr(
            "manifest.json", json.dumps({"format": backups.FORMAT, "version": 1})
        )
        zf.writestr("documents/../../escape.py", "x")
    with pytest.raises(backups.BackupProblem, match="unsafe"):
        backups.read_manifest(evil)


def test_restore_puts_things_back_and_keeps_what_it_replaces(
    home: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    archive = make(home, tmp_path / "out")
    documents, config = tmp_path / "new_docs", tmp_path / "new_config"
    documents.mkdir()
    (documents / "tool.py").write_text("print('changed')\n")
    config.mkdir()
    (config / "launcher.toml").write_text("resume = false\n")
    done = backups.restore(archive, documents, config)
    assert done.added == ["proj"] and done.replaced == ["tool.py"]
    assert (documents / "tool.py").read_text() == "print(1)\n"
    assert (documents / "proj" / "src" / "app.py").read_text() == "x = 1\n"
    assert any((documents / "backups").iterdir())  # the changed tool.py is kept
    assert (config / "launcher.toml").read_text() == "resume = true\n"
    assert done.config == ["launcher.toml"]
    assert not [p for p in documents.iterdir() if p.name.startswith(".restore_")]


def test_restore_can_leave_settings_alone(
    home: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    archive = make(home, tmp_path / "out")
    documents, config = tmp_path / "d", tmp_path / "c"
    config.mkdir()
    (config / "launcher.toml").write_text("mine = 1\n")
    done = backups.restore(archive, documents, config, settings=False)
    assert (config / "launcher.toml").read_text() == "mine = 1\n" and not done.config


def test_restoring_the_same_again_changes_nothing(
    home: tuple[Path, Path, Path], tmp_path: Path
) -> None:
    import shutil

    documents, config, _ = home
    shutil.rmtree(documents / "proj" / "__pycache__")  # never in a backup
    archive = make(home, tmp_path / "out")
    done = backups.restore(archive, documents, config)
    assert sorted(done.unchanged) == ["proj", "tool.py"] and not done.replaced
