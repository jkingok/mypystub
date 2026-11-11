"""Copying the bundled examples into private storage on Android."""

from pathlib import Path

from mypystub import examples_copy


def make_examples(root: Path) -> Path:
    """A small examples tree: a script, a data file beside it, and a project."""
    (root / "basics").mkdir(parents=True)
    (root / "basics" / "hello.py").write_text("print('hi')\n", encoding="utf-8")
    (root / "basics" / "data.csv").write_text("a,b\n1,2\n", encoding="utf-8")
    (root / "projects" / "tool").mkdir(parents=True)
    (root / "projects" / "tool" / "pyproject.toml").write_text(
        "[project]\nname = 'tool'\n", encoding="utf-8"
    )
    return root


def test_copy_keeps_scripts_and_data_beside_each_other(tmp_path: Path) -> None:
    source = make_examples(tmp_path / "source")
    dest = tmp_path / "dest"

    examples_copy.copy_tree(source, dest)

    # The data file is copied too, so a script can find it with pathlib
    assert (dest / "basics" / "hello.py").read_text(encoding="utf-8") == "print('hi')\n"
    assert (dest / "basics" / "data.csv").read_text(encoding="utf-8") == "a,b\n1,2\n"
    assert (dest / "projects" / "tool" / "pyproject.toml").exists()


def test_refresh_copies_when_nothing_is_there(tmp_path: Path) -> None:
    source = make_examples(tmp_path / "source")
    dest = tmp_path / "cache" / "examples"

    result = examples_copy.refresh_copy(source, dest)

    assert result == dest
    assert (dest / "basics" / "hello.py").exists()


def test_refresh_leaves_an_unchanged_copy_alone(tmp_path: Path) -> None:
    source = make_examples(tmp_path / "source")
    dest = tmp_path / "dest"
    examples_copy.refresh_copy(source, dest)
    marker = dest / "basics" / "written_by_script.txt"
    marker.write_text("kept", encoding="utf-8")

    examples_copy.refresh_copy(source, dest)

    # Nothing changed in the source, so the copy isn't rebuilt
    assert marker.read_text(encoding="utf-8") == "kept"


def test_refresh_rebuilds_when_the_source_changes(tmp_path: Path) -> None:
    source = make_examples(tmp_path / "source")
    dest = tmp_path / "dest"
    examples_copy.refresh_copy(source, dest)
    (dest / "basics" / "stale.txt").write_text("old", encoding="utf-8")
    (source / "basics" / "hello.py").write_text("print('new')\n", encoding="utf-8")

    examples_copy.refresh_copy(source, dest)

    assert (dest / "basics" / "hello.py").read_text(
        encoding="utf-8"
    ) == "print('new')\n"
    assert not (dest / "basics" / "stale.txt").exists()


def test_hash_changes_with_content_and_names(tmp_path: Path) -> None:
    source = make_examples(tmp_path / "source")
    before = examples_copy.content_hash(source)

    (source / "basics" / "hello.py").write_text("print('x')\n", encoding="utf-8")
    after_edit = examples_copy.content_hash(source)
    (source / "basics" / "renamed.py").write_text("", encoding="utf-8")
    after_add = examples_copy.content_hash(source)

    assert len({before, after_edit, after_add}) == 3


def test_android_copies_into_cache_and_other_platforms_use_the_bundle(
    tmp_path: Path,
) -> None:
    bundled = make_examples(tmp_path / "bundled")
    cache = tmp_path / "cache"

    android = examples_copy.examples_location(bundled, cache, "android")
    desktop = examples_copy.examples_location(bundled, cache, "darwin")

    assert android == cache / "examples"
    assert (android / "basics" / "data.csv").exists()
    assert desktop == bundled
    assert not (cache / "examples" / "unused").exists()
