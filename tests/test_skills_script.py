"""The single-file script skill: valid frontmatter, and code that parses (#356)."""

from __future__ import annotations

import ast
import re
import textwrap
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
SKILL = ROOT / "skills/mypystub-script/SKILL.md"
BLOCKS = re.findall(
    r"```python\n(.*?)```", SKILL.read_text(encoding="utf-8"), re.DOTALL
)
# PEP 723's own pattern for an inline metadata block
METADATA = re.compile(
    r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
)


def frontmatter(text: str) -> dict[str, str]:
    block = text[4 : text.index("\n---\n", 4)]
    pairs = (line.split(":", 1) for line in block.splitlines() if ":" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def test_the_skill_has_a_name_and_a_description() -> None:
    text = SKILL.read_text(encoding="utf-8")
    assert text.startswith("---\n")
    fields = frontmatter(text)
    assert fields["name"] == "mypystub-script"
    assert len(fields["description"]) > 40


def test_every_example_parses() -> None:
    assert len(BLOCKS) >= 2
    for block in BLOCKS:
        ast.parse(textwrap.dedent(block))


def test_the_file_shape_starts_with_pep_723_metadata() -> None:
    shape = BLOCKS[0]
    match = METADATA.search(shape)
    assert match is not None and match.start() == 0
    assert match["type"] == "script"
    lines = match["content"].splitlines(keepends=True)
    toml = "".join(line[2:] if line.startswith("# ") else line[1:] for line in lines)
    metadata = tomllib.loads(toml)
    assert "requires-python" in metadata and "toga" in metadata["dependencies"]


def test_the_ui_example_needs_no_mypystub() -> None:
    ui = textwrap.dedent(BLOCKS[1])
    imports = {
        alias.name.split(".")[0]
        for node in ast.walk(ast.parse(ui))
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(ast.parse(ui))
        if isinstance(node, ast.ImportFrom)
    }
    assert "mypystub" not in imports
    assert "content_stack" in ui and "main_loop()" in ui
    assert "call_soon_threadsafe" in ui


def test_the_skills_point_at_each_other() -> None:
    app = (ROOT / "skills/mypystub-app/SKILL.md").read_text(encoding="utf-8")
    assert "mypystub-script" in frontmatter(app)["description"]
    assert (
        "mypystub-app" in frontmatter(SKILL.read_text(encoding="utf-8"))["description"]
    )
