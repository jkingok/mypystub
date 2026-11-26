"""Instructions for coding agents in the project template, and its skill (#322)."""

from __future__ import annotations

from pathlib import Path

import pytest

from mypystub import new_items

ROOT = Path(__file__).parent.parent
SKILL = ROOT / "skills/mypystub-app/SKILL.md"
TEMPLATE = new_items.PROJECT_TEMPLATE


def frontmatter(text: str) -> dict[str, str]:
    """The YAML frontmatter's top-level ``key: value`` lines."""
    assert text.startswith("---\n"), "the skill starts with frontmatter"
    block = text[4 : text.index("\n---\n", 4)]
    pairs = (line.split(":", 1) for line in block.splitlines() if ":" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def test_the_skill_has_a_name_and_a_description() -> None:
    fields = frontmatter(SKILL.read_text(encoding="utf-8"))
    assert fields["name"] == "mypystub-app"
    assert len(fields["description"]) > 40


def test_the_template_links_the_skill() -> None:
    link = TEMPLATE / ".claude/skills/mypystub-app/SKILL.md"
    assert link.is_symlink() and link.resolve() == SKILL.resolve()


def test_claude_md_imports_agents_md() -> None:
    assert (TEMPLATE / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"


def framework_files() -> list[str]:
    """What a project mustn't edit: its links, and the bootstrap's own files."""
    package = TEMPLATE / "src/app_template"
    linked = [p.name for p in package.glob("*.py") if p.is_symlink()]
    return sorted({*linked, "bootstrap.py", "__main__.py"})


@pytest.mark.parametrize("name", ["AGENTS.md", "SKILL"])
def test_the_dont_touch_lists_name_every_shared_file(name: str) -> None:
    """Every file updates replace is named, so the lists can't drift (#312)."""
    path = SKILL if name == "SKILL" else TEMPLATE / name
    text = path.read_text(encoding="utf-8")
    missing = [f for f in framework_files() if f not in text]
    assert not missing
    assert "android/java/" in text and "generate_icons.py" in text


def test_a_new_project_carries_them(tmp_path: Path) -> None:
    project = new_items.create_project(tmp_path, "Weather Now")
    skill = project / ".claude/skills/mypystub-app/SKILL.md"
    assert skill.is_file() and not skill.is_symlink()
    assert frontmatter(skill.read_text(encoding="utf-8"))["name"] == "mypystub-app"
    agents = (project / "AGENTS.md").read_text(encoding="utf-8")
    assert "src/weather_now/app.py" in agents and "app_template" not in agents
    assert (project / "CLAUDE.md").read_text(encoding="utf-8") == "@AGENTS.md\n"


def test_the_skill_is_public_safe() -> None:
    """It's published from main: no internal repository or private links."""
    text = SKILL.read_text(encoding="utf-8").lower()
    assert "mypystub-internal" not in text
    assert "claude.ai/code/session" not in text
