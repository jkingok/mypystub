"""Zipapps (.pyz): scanned, described and run like projects (#124).

They are trusted as they are: nothing is validated or extracted, and a broken
archive is just a run-time error.
"""

import sys
import zipfile
from pathlib import Path

import pytest

from mypystub import info_pages, scan
from mypystub.runner import RunContext, entry_target, target_for

MAIN = "print('hello from', __name__, sys.argv[1:])\n"
METADATA = """Metadata-Version: 2.1
Name: tools
Version: 1.2.3
Summary: Some zipped tools
Requires-Dist: httpx
Project-URL: Homepage, https://example.org
Description-Content-Type: text/markdown

# Tools

Zipped <b>up</b>.
"""
ENTRY_POINTS = """[console_scripts]
greet = tools.cli:greet
zeta = tools.cli:zeta

[gui_scripts]
window = tools.cli:window

[tools.plugins]
plug = tools.cli:PLUG
"""
CLI = """import sys

PLUG = 1

def greet():
    print("greeting", sys.argv)

def zeta():
    print("zeta")
"""


def make_zipapp(
    path: Path, *, main: str | None = None, metadata: bool = False, entry: bool = False
) -> Path:
    """Write a .pyz with the given pieces."""
    with zipfile.ZipFile(path, "w") as archive:
        if main is not None:
            archive.writestr("__main__.py", main)
        archive.writestr("tools/__init__.py", "")
        archive.writestr("tools/cli.py", CLI)
        if metadata:
            archive.writestr("tools-1.2.3.dist-info/METADATA", METADATA)
        if entry:
            archive.writestr("tools-1.2.3.dist-info/entry_points.txt", ENTRY_POINTS)
    return path


def test_a_pyz_is_a_zipapp_row(tmp_path: Path) -> None:
    """Even a bare archive is listed, titled by its file name."""
    make_zipapp(tmp_path / "bare.pyz", main="import sys\n" + MAIN)
    (row,) = scan.scan_all_prototypes(tmp_path)
    assert row["kind"] == "zipapp"
    assert row["title"] == "bare"
    assert row["entry_point"] == tmp_path / "bare.pyz"
    assert row["folder_root"] == tmp_path / "bare.pyz"
    assert row["dependencies"] == []


def test_metadata_gives_title_subtitle_and_entry_points(tmp_path: Path) -> None:
    """dist-info fills in the description; several entry points make a package."""
    make_zipapp(tmp_path / "tools.pyz", main="", metadata=True, entry=True)
    (row,) = scan.scan_all_prototypes(tmp_path)
    assert row["kind"] == "package"
    assert row["subtitle"] == "Some zipped tools"
    assert row["project_dir"] == tmp_path / "tools.pyz"
    rows = scan.entry_rows(row)
    assert [(r["title"], r["subtitle"]) for r in rows] == [
        ("greet", "Console · tools.cli:greet"),
        ("plug", "tools.plugins · tools.cli:PLUG"),
        ("window", "GUI · tools.cli:window"),
        ("zeta", "Console · tools.cli:zeta"),
    ]


def test_one_entry_point_is_the_implied_entry(tmp_path: Path) -> None:
    """A single entry point runs when the zipapp is tapped."""
    path = make_zipapp(tmp_path / "one.pyz", metadata=True)
    with zipfile.ZipFile(path, "a") as archive:
        archive.writestr(
            "tools-1.2.3.dist-info/entry_points.txt",
            "[console_scripts]\ngreet = tools.cli:greet\n",
        )
    (row,) = scan.scan_all_prototypes(tmp_path)
    assert row["kind"] == "zipapp"
    assert row["entry"].name == "greet"


def test_unreadable_archive_is_still_listed(tmp_path: Path) -> None:
    """No scanning for problems: a bad file is a row, and fails when run."""
    (tmp_path / "broken.pyz").write_bytes(b"not a zip")
    (row,) = scan.scan_all_prototypes(tmp_path)
    assert row["kind"] == "zipapp" and row["title"] == "broken"


def test_running_main_from_the_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """__main__.py runs as __main__ with the archive importable; state restored."""
    path = make_zipapp(tmp_path / "app.pyz", main="import sys\n" + MAIN)
    before = list(sys.path)
    with RunContext(target_for(path, path), argv=["a", "b"]) as run:
        run.run()
    assert capsys.readouterr().out == "hello from __main__ ['a', 'b']\n"
    assert sys.path == before and "tools" not in sys.modules


def test_running_an_entry_point_from_the_archive(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """module:attr entries are imported from the archive and called."""
    path = make_zipapp(tmp_path / "app.pyz", main="")
    target = entry_target("greet", "tools.cli:greet", "other", path, path)
    assert target.workdir == tmp_path  # an archive is not a working directory
    with RunContext(target, argv=["x"]) as run:
        run.run()
    assert capsys.readouterr().out == "greeting ['greet', 'x']\n"
    assert "tools" not in sys.modules


def test_a_broken_archive_fails_at_run_time(tmp_path: Path) -> None:
    """The error appears when it runs, like python broken.pyz."""
    path = tmp_path / "broken.pyz"
    path.write_bytes(b"not a zip")
    with pytest.raises(Exception), RunContext(target_for(path, path)) as run:  # noqa: B017
        run.run()


def test_info_page_for_a_zipapp(tmp_path: Path) -> None:
    """Info shows the dist-info details and the entry script, escaped."""
    path = make_zipapp(
        tmp_path / "tools.pyz", main="print('<b>hi</b>')\n", metadata=True, entry=True
    )
    page = info_pages.zipapp_info_html(path, "tools")
    assert "<h1>tools</h1>" in page and "Some zipped tools" in page
    assert "Version: 1.2.3" in page and "<code>httpx</code>" in page
    assert "<code>greet</code>: Console · <code>tools.cli:greet</code>" in page
    assert '<a href="https://example.org">https://example.org</a>' in page
    assert "<h2>README</h2>" in page and "Zipped &lt;b&gt;up&lt;/b&gt;." in page
    assert "<h2>Source</h2>" in page and "&lt;b&gt;hi&lt;/b&gt;" in page
    assert str(tmp_path) not in page


def test_info_page_for_a_bare_or_broken_zipapp(tmp_path: Path) -> None:
    """Missing metadata shows what exists; an unreadable file says so."""
    bare = make_zipapp(tmp_path / "bare.pyz", main="x = 1\n")
    page = info_pages.zipapp_info_html(bare, "bare")
    assert "<h1>bare</h1>" in page and "Entry points" not in page
    (tmp_path / "bad.pyz").write_bytes(b"nope")
    assert "Couldn't read" in info_pages.zipapp_info_html(tmp_path / "bad.pyz", "bad")
