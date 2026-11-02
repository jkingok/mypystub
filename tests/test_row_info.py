"""Tests for what Info and Setup say about each kind of launcher row."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from mypystub import row_info


@pytest.mark.parametrize(
    ("row", "kind"),
    [
        (SimpleNamespace(title="Examples", category="Examples"), "category"),
        (SimpleNamespace(title="..", categories=True), "up"),
        (SimpleNamespace(title="..", folder=Path("x")), "up"),
        (SimpleNamespace(title="a", folder=Path("a"), kind="folder"), "folder"),
        (SimpleNamespace(title="top", kind="script"), "script"),
        (SimpleNamespace(title="Hello", kind="project"), "project"),
        (SimpleNamespace(title="?"), "other"),
    ],
)
def test_row_types(row: object, kind: str) -> None:
    """Rows are told apart by the keys the launcher gives them."""
    assert row_info.row_type(row) == kind


def test_only_scripts_and_projects_are_runnable() -> None:
    """Only rows that run when tapped have run settings."""
    runnable = [k for k in ("category", "up", "folder", "script", "project", "other")]
    assert [k for k in runnable if row_info.runnable(k)] == ["script", "project"]  # type: ignore[arg-type]


def test_readme_names_in_order_of_preference(tmp_path: Path) -> None:
    """README.md wins over README.txt and README; letter case doesn't matter."""
    assert row_info.find_readme(tmp_path) is None
    (tmp_path / "README").write_text("plain")
    assert row_info.find_readme(tmp_path) == tmp_path / "README"
    (tmp_path / "readme.txt").write_text("text")
    assert row_info.find_readme(tmp_path) == tmp_path / "readme.txt"
    (tmp_path / "ReadMe.md").write_text("# md")
    assert row_info.find_readme(tmp_path) == tmp_path / "ReadMe.md"


def test_a_folder_named_readme_is_not_a_readme(tmp_path: Path) -> None:
    """Only files count."""
    (tmp_path / "README").mkdir()
    assert row_info.find_readme(tmp_path) is None


def test_missing_folder_has_no_readme(tmp_path: Path) -> None:
    """A folder that has gone away is treated as having no README."""
    assert row_info.find_readme(tmp_path / "gone") is None


def test_run_with_messages_fit_the_row() -> None:
    """Each kind of row that can't run says why, by name."""
    examples = row_info.run_with_message("category", "Examples")
    assert examples.startswith("Examples holds the bundled examples.")
    assert "swipe a script or project" in examples
    documents = row_info.run_with_message("category", "Documents")
    assert documents.startswith("Documents holds your own scripts")
    assert row_info.run_with_message("folder", "tools").startswith(
        "tools is a folder, so there's nothing to run."
    )
    assert row_info.run_with_message("up", "..", "Examples/basics") == (
        "This row goes back to Examples/basics, so there's nothing to run."
    )


def test_info_without_a_readme_says_what_the_folder_holds() -> None:
    """Info on a folder with no README says so, and what's in it."""
    message = row_info.no_readme_message("folder", "tools", "3 scripts, 1 subfolder")
    assert message == (
        "tools has no README to show. It holds 3 scripts, 1 subfolder. "
        "Add a README.md to describe it."
    )
    assert "tools is empty." in row_info.no_readme_message(
        "folder", "tools", "Empty folder"
    )
    documents = row_info.no_readme_message("category", "Documents", "1 script")
    assert documents.startswith("Documents holds your own scripts and projects.")


def test_info_on_up_rows() -> None:
    """A ".." row says where it leads."""
    assert row_info.up_info_message("the categories") == (
        "This row goes back to the categories, so there's nothing to describe."
    )


def test_prototype_summary() -> None:
    """Scripts and projects show their description and dependencies."""
    row = SimpleNamespace(subtitle="Greets you.", dependencies=["humanize", "rich"])
    assert row_info.prototype_summary(row) == (
        "Greets you.\n\nDependencies: humanize, rich"
    )
    bare = SimpleNamespace(subtitle="Plain.", dependencies=[])
    assert row_info.prototype_summary(bare) == "Plain.\n\nNo dependencies."
