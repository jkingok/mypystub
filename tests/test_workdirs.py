"""Working-folder choices: describing, checking and resolving them (#308)."""

from pathlib import Path

from mypystub import workdirs
from mypystub.run_settings import RunSettings


def test_choices_in_words() -> None:
    assert workdirs.describe(workdirs.SCRIPT) == "Script's folder"
    assert workdirs.describe(workdirs.CACHE) == "Cache"
    assert workdirs.describe(workdirs.documents("data/out")) == "Documents › data › out"
    assert workdirs.describe(workdirs.documents("")) == "Documents"


def test_only_safe_choices_are_valid() -> None:
    assert workdirs.is_valid("script") and workdirs.is_valid("cache")
    assert workdirs.is_valid("documents:a/b") and workdirs.is_valid("documents:")
    for bad in (None, "", "elsewhere", "documents:../up", "documents:/abs"):
        assert not workdirs.is_valid(bad)


def test_examples_default_to_the_cache() -> None:
    assert workdirs.default_for("Examples") == workdirs.CACHE
    assert workdirs.default_for("Documents") == workdirs.SCRIPT


def test_the_cache_folder_is_per_thing(tmp_path: Path) -> None:
    folder, notice = workdirs.resolve(
        workdirs.CACHE,
        script_folder=tmp_path / "s",
        cache=tmp_path / "cache",
        documents_root=tmp_path / "docs",
        key="Examples/basics/fancy.py",
    )
    assert folder == tmp_path / "cache/workdirs/Examples/basics/fancy.py"
    assert folder.is_dir() and notice is None


def test_a_documents_folder_and_a_missing_one(tmp_path: Path) -> None:
    (tmp_path / "docs" / "out").mkdir(parents=True)
    args = {
        "script_folder": tmp_path / "s",
        "cache": tmp_path / "c",
        "documents_root": tmp_path / "docs",
        "key": "k",
    }
    assert workdirs.resolve("documents:out", **args) == (tmp_path / "docs/out", None)
    folder, notice = workdirs.resolve("documents:gone", **args)
    assert folder == tmp_path / "s" and notice and "Documents › gone" in notice


def test_the_choice_is_saved_with_the_settings() -> None:
    table = RunSettings(["a"], {"X": "1"}, "cache").to_table()
    assert table["workdir"] == "cache"
    assert RunSettings.from_table(table).workdir == "cache"
    assert RunSettings.from_table({"args": []}).workdir is None
    assert "workdir" not in RunSettings().to_table()
