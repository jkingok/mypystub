"""Tests for scripts/collect_changes.py, the release step for "What's New" (#126)."""

import importlib.util
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "collect_changes.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not bundled on device"
)


def load():
    """Import the script as a module."""
    spec = importlib.util.spec_from_file_location("collect_changes", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A project folder with an empty changes/ and What's New file."""
    (tmp_path / "changes").mkdir()
    templates = tmp_path / "src" / "mypystub" / "resources" / "templates"
    templates.mkdir(parents=True)
    (templates / "changes.md").write_text("# What's New\n", encoding="utf-8")
    return tmp_path


def headings(text: str) -> int:
    """How many release sections (not their ### groups) a file has."""
    return sum(1 for line in text.splitlines() if line.startswith("## "))


def fragment(repo: Path, name: str, text: str) -> None:
    """Add a change fragment."""
    (repo / "changes" / name).write_text(text, encoding="utf-8")


def whats_new(repo: Path) -> str:
    """The What's New file as the app shows it."""
    return (repo / "src/mypystub/resources/templates/changes.md").read_text()


def archive(repo: Path) -> str:
    """The archive, or "" if there isn't one."""
    path = repo / "changes-archive.md"
    return path.read_text() if path.exists() else ""


def test_fragments_become_a_section_grouped_by_type(repo: Path) -> None:
    """New and Fixed groups, oldest PR first; misc fragments aren't user-facing."""
    fragment(repo, "130.feature.md", "Input is echoed.")
    fragment(repo, "129.feature.md", "New users open on Help.")
    fragment(repo, "131.bugfix.md", "Setup menu layout.\n")
    fragment(repo, "132.misc.md", "Refactor nothing users see.")
    load().collect(repo, "2026.11.3.1", date(2026, 11, 3))
    assert whats_new(repo) == (
        "# What's New\n\n"
        "## 2026.11.3.1 (2026-11-03)\n\n"
        "### New\n\n- New users open on Help.\n- Input is echoed.\n\n"
        "### Fixed\n\n- Setup menu layout.\n"
    )
    assert list((repo / "changes").iterdir()) == []  # all collected, misc included


def test_multi_line_fragments_are_one_bullet(repo: Path) -> None:
    """Wrapped text in a fragment becomes a single line."""
    fragment(repo, "1.feature.md", "A long\nsentence that wraps.\n")
    load().collect(repo, "2026.11.3.1", date(2026, 11, 3))
    assert "- A long sentence that wraps.\n" in whats_new(repo)


def test_new_sections_go_above_older_ones(repo: Path) -> None:
    """Newest first."""
    fragment(repo, "1.feature.md", "First.")
    load().collect(repo, "2026.11.1.1", date(2026, 11, 1))
    fragment(repo, "2.feature.md", "Second.")
    load().collect(repo, "2026.11.3.1", date(2026, 11, 3))
    text = whats_new(repo)
    assert text.index("2026.11.3.1") < text.index("2026.11.1.1")


def test_same_day_builds_share_one_section(repo: Path) -> None:
    """A second build on the same day adds to the day's section, under its version."""
    fragment(repo, "1.feature.md", "Morning.")
    load().collect(repo, "2026.11.3.1", date(2026, 11, 3))
    fragment(repo, "2.feature.md", "Afternoon.")
    fragment(repo, "3.bugfix.md", "Fix.")
    load().collect(repo, "2026.11.3.2", date(2026, 11, 3))
    text = whats_new(repo)
    assert headings(text) == 1 and "## 2026.11.3.2 (2026-11-03)" in text
    assert "- Morning.\n- Afternoon." in text and "### Fixed\n\n- Fix." in text


def test_no_fragments_changes_nothing(repo: Path) -> None:
    """A build with no user-facing changes leaves the files alone."""
    before = whats_new(repo)
    load().collect(repo, "2026.11.3.1", date(2026, 11, 3))
    fragment(repo, "5.misc.md", "Internal.")
    load().collect(repo, "2026.11.3.2", date(2026, 11, 3))
    assert whats_new(repo) == before and archive(repo) == ""
    assert list((repo / "changes").iterdir()) == []  # misc is still consumed


def test_old_sections_are_archived_but_thirty_days_and_three_sections_stay(
    repo: Path,
) -> None:
    """Anything over 30 days old goes, unless it would leave fewer than three."""
    mod = load()
    for day, version in [
        (date(2026, 9, 1), "2026.9.1.1"),
        (date(2026, 9, 29), "2026.9.29.1"),
        (date(2026, 10, 1), "2026.10.1.1"),
        (date(2026, 10, 20), "2026.10.20.1"),
    ]:
        fragment(repo, "1.feature.md", f"Change on {day}.")
        mod.collect(repo, version, day)
    fragment(repo, "2.feature.md", "Today.")
    mod.collect(repo, "2026.11.3.1", date(2026, 11, 3))
    text = whats_new(repo)
    # 3 November: from 4 October on stays (30 days); the 1 October section is
    # older but would leave only 3, so it stays too. 29 and 1 September go.
    assert "2026.11.3.1" in text and "2026.10.20.1" in text and "2026.10.1.1" in text
    assert "2026.9.29.1" not in text and "2026.9.1.1" not in text
    assert "2026.9.29.1" in archive(repo) and "2026.9.1.1" in archive(repo)
    assert archive(repo).index("2026.9.29.1") < archive(repo).index("2026.9.1.1")


def test_a_quiet_month_keeps_the_newest_three(repo: Path) -> None:
    """With little recent activity, the last three sections are still shown."""
    mod = load()
    for number, (day, version) in enumerate(
        [
            (date(2026, 6, 1), "2026.6.1.1"),
            (date(2026, 7, 1), "2026.7.1.1"),
            (date(2026, 8, 1), "2026.8.1.1"),
            (date(2026, 9, 1), "2026.9.1.1"),
        ]
    ):
        fragment(repo, f"{number}.feature.md", f"Change {number}.")
        mod.collect(repo, version, day)
    text = whats_new(repo)
    assert headings(text) == 3 and "2026.6.1.1" not in text
    assert "2026.6.1.1" in archive(repo)


def test_command_line(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The command line collects for a version and prints a summary."""
    fragment(repo, "1.feature.md", "Hello.")
    load().main(["2026.11.3.1", "--root", str(repo), "--today", "2026-11-03"])
    assert "## 2026.11.3.1 (2026-11-03)" in whats_new(repo)
    assert "1 change" in capsys.readouterr().out


def test_rejects_a_bad_version(repo: Path) -> None:
    """The version has to look like YYYY.M.D.N (it is the tag, too)."""
    fragment(repo, "1.feature.md", "Hello.")
    with pytest.raises(ValueError, match="version"):
        load().collect(repo, "v1", date(2026, 11, 3))
    assert (repo / "changes" / "1.feature.md").exists()  # nothing was consumed
