"""The READMEs the Info view shows must render as they are written (#108)."""

import re
from pathlib import Path

import pytest

import mypystub
from mypystub.pages import readme_html

BUNDLED = Path(mypystub.__file__).parent / "resources" / "examples"
READMES = sorted(BUNDLED.rglob("README.md"))


@pytest.mark.parametrize("path", READMES, ids=lambda p: str(p.relative_to(BUNDLED)))
def test_nested_lists_use_four_space_indents(path: Path) -> None:
    """Python-Markdown nests a list only when it is indented four spaces."""
    two_space = [
        number
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if re.match(r"^ {1,3}[-*+] ", line)
    ]
    assert not two_space, f"indent nested items by 4 spaces: lines {two_space}"


def test_examples_readme_nests_each_folders_scripts() -> None:
    """The scripts of each folder render under the folder, as a nested list."""
    html = readme_html((BUNDLED / "README.md").read_text(encoding="utf-8"), "README.md")
    assert html.count("<ul>") > 1
    assert re.search(r"<code>basics/</code>\s*<ul>", html)


def test_examples_readme_is_written_for_users() -> None:
    """Info shows this in the app, so it leaves repository details out."""
    text = (BUNDLED / "README.md").read_text(encoding="utf-8").lower()
    for developer_word in ("pytest", "symlink", "claude.md", "briefcase bundles"):
        assert developer_word not in text
