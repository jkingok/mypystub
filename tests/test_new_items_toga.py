"""New projects use the launcher's Toga, so they run on what MyPyStub tested.

A different Toga (or the Rubicon it brings) on one side would make a project
behave differently built than it did in MyPyStub.
"""

import tomllib
from pathlib import Path

import pytest

from mypystub import new_items

ROOT = Path(__file__).parent.parent
PLATFORMS = ["macOS", "linux", "windows", "iOS", "android"]


# Widgets the launcher uses for its own features, not Toga itself (#289)
LAUNCHER_WIDGETS = ("toga-console",)


def toga_requirements(requires: list[str]) -> set[str]:
    """The Toga and Travertino requirements in a Briefcase `requires` list."""
    return {
        r
        for r in requires
        if r.startswith(("toga", "travertino")) and not r.startswith(LAUNCHER_WIDGETS)
    }


def app_table(path: Path, name: str) -> dict:
    """The Briefcase app table called `name` in a pyproject.toml."""
    config = tomllib.loads(path.read_text(encoding="utf-8"))
    return config["tool"]["briefcase"]["app"][name]


@pytest.fixture(scope="module")
def tables() -> tuple[dict, dict]:
    """The launcher's app table, and the project template's."""
    template = new_items.PROJECT_TEMPLATE / "pyproject.toml"
    return app_table(ROOT / "pyproject.toml", "mypystub"), app_table(
        template, "app_template"
    )


def test_the_shared_toga_matches(tables: tuple[dict, dict]) -> None:
    launcher, project = tables
    assert toga_requirements(project["requires"]) == toga_requirements(
        launcher["requires"]
    )


@pytest.mark.parametrize("platform", PLATFORMS)
def test_each_backend_matches(tables: tuple[dict, dict], platform: str) -> None:
    launcher, project = tables
    assert toga_requirements(project[platform]["requires"]) == toga_requirements(
        launcher[platform]["requires"]
    )


def test_ios_uses_the_same_briefcase_template(tables: tuple[dict, dict]) -> None:
    """The template branch carries the Rubicon run-loop fix both need."""
    launcher, project = tables
    assert project["iOS"].get("template_branch") == launcher["iOS"].get(
        "template_branch"
    )
