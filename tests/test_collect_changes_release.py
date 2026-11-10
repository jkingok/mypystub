"""Release notes for a GitHub Release, from What's New (#202)."""

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


def test_the_body_is_the_section_without_its_heading(repo: Path) -> None:
    """The Markdown the app shows, minus the version line a Release replaces."""
    module = load()
    (repo / "changes" / "1.feature.md").write_text("Added a thing.")
    (repo / "changes" / "2.bugfix.md").write_text("Fixed a thing.")
    module.collect(repo, "2026.11.3.1", date(2026, 11, 3))
    text = (repo / module.WHATS_NEW).read_text(encoding="utf-8")
    body = module.release_notes_for(text, "2026.11.3.1")
    assert body == "### New\n\n- Added a thing.\n\n### Fixed\n\n- Fixed a thing."
    assert "2026.11.3.1" not in body and "## " not in body.split("\n", 1)[0][:2]


def test_a_build_without_user_facing_changes_says_so(repo: Path) -> None:
    """Nothing for this version, an older section, or an empty file."""
    module = load()
    (repo / "changes" / "1.feature.md").write_text("Added a thing.")
    module.collect(repo, "2026.11.3.1", date(2026, 11, 3))
    text = (repo / module.WHATS_NEW).read_text(encoding="utf-8")
    assert module.release_notes_for(text, "2026.11.3.2") == module.NO_CHANGES
    assert module.release_notes_for("# What's New\n", "2026.11.3.1") == (
        "No user-facing changes."
    )


def test_a_day_with_two_builds_shares_one_section(repo: Path) -> None:
    """The section carries the latest build's version, as the app shows it."""
    module = load()
    (repo / "changes" / "1.feature.md").write_text("First.")
    module.collect(repo, "2026.11.3.1", date(2026, 11, 3))
    (repo / "changes" / "2.feature.md").write_text("Second.")
    module.collect(repo, "2026.11.3.2", date(2026, 11, 3))
    text = (repo / module.WHATS_NEW).read_text(encoding="utf-8")
    body = module.release_notes_for(text, "2026.11.3.2")
    assert "- First." in body and "- Second." in body
    assert module.release_notes_for(text, "2026.11.3.1") == module.NO_CHANGES


def test_the_command_line_prints_it(
    repo: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """--release-notes prints Markdown; --notes still prints plain text."""
    module = load()
    (repo / "changes" / "1.feature.md").write_text("Added a thing.")
    module.collect(repo, "2026.11.3.1", date(2026, 11, 3))
    module.main(["2026.11.3.1", "--release-notes", "--root", str(repo)])
    assert capsys.readouterr().out.strip() == "### New\n\n- Added a thing."
    module.main(["2026.11.3.1", "--notes", "--root", str(repo)])
    assert capsys.readouterr().out.strip() == "New:\n• Added a thing."
