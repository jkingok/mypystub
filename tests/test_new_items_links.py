"""The project template's shared files: links in the repository, copies in a project.

Android's Back, the documents provider and generate_icons.py are symbolic links
to the launcher's own, so each exists once. A checkout without links leaves
one-line stand-ins, which New spots and refuses (template_problems).
"""

import shutil
from pathlib import Path

import pytest

from mypystub import new_items

ROOT = Path(__file__).parent.parent
SHARED = {
    "android/java/app_template/android/AppDocumentsProvider.java": (
        "assets/android/java/au/id/jking/mypystub/AppDocumentsProvider.java"
    ),
    "android/java/app_template/android/PyBackCallback.java": (
        "assets/android/java/au/id/jking/mypystub/PyBackCallback.java"
    ),
    "src/app_template/android_back.py": "src/mypystub/android_back.py",
    "src/app_template/hooks.py": "src/mypystub/hooks.py",
    "src/app_template/logfile.py": "src/mypystub/logfile.py",
    "src/app_template/run_status.py": "src/mypystub/run_status.py",
    "src/app_template/script_tab.py": "src/mypystub/script_tab.py",
    ".claude/skills/mypystub-app/SKILL.md": "skills/mypystub-app/SKILL.md",
    "generate_icons.py": "generate_icons.py",
}


@pytest.mark.parametrize(("link", "target"), SHARED.items())
def test_each_shared_file_is_a_working_link(link: str, target: str) -> None:
    """Relative links that resolve, so a checkout anywhere keeps them."""
    path = new_items.PROJECT_TEMPLATE / link
    assert path.is_symlink() and not Path(path.readlink()).is_absolute()
    assert path.resolve() == (ROOT / target).resolve()


def test_this_checkout_has_no_template_problems() -> None:
    assert new_items.template_problems() == []


def test_a_new_project_has_real_files_with_its_own_package(tmp_path: Path) -> None:
    project = new_items.create_project(tmp_path, "Weather Now")
    assert not [p for p in project.rglob("*") if p.is_symlink()]
    java = project / "android/java/weather_now/android/PyBackCallback.java"
    back = (project / "src/weather_now/android_back.py").read_text()
    assert java.read_text().startswith("package weather_now.android;")
    assert '"weather_now.android.PyBackCallback"' in back
    assert new_items.SHARED_PACKAGE not in back


@pytest.fixture
def damaged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the template as a clone without symbolic links would have it."""
    template = tmp_path / "template"
    shutil.copytree(new_items.PROJECT_TEMPLATE, template, symlinks=True)
    for link in SHARED:
        path = template / link
        target = str(path.readlink())
        path.unlink()
        path.write_text(target)  # what git writes when it can't make a link
    monkeypatch.setattr(new_items, "PROJECT_TEMPLATE", template)
    return template


def test_link_stand_ins_are_found(damaged: Path) -> None:
    problems = new_items.template_problems(damaged)
    assert len(problems) == len(SHARED)
    assert all("checked out as a text file" in p for p in problems)


def test_a_broken_link_is_found(tmp_path: Path) -> None:
    (tmp_path / "gone.py").symlink_to("../nowhere/gone.py")
    assert new_items.template_problems(tmp_path) == [
        "gone.py (a link to something missing)"
    ]


def test_new_refuses_a_damaged_template(damaged: Path, tmp_path: Path) -> None:
    out = tmp_path / "out"
    out.mkdir()
    with pytest.raises(new_items.TemplateProblem, match="core.symlinks"):
        new_items.create_project(
            out,
            "Weather Now",
            "",
            "",
            "",
        )
    assert list(out.iterdir()) == []


def test_ordinary_short_files_arent_mistaken_for_links(tmp_path: Path) -> None:
    (tmp_path / "__init__.py").write_text('"""A package."""\n')
    (tmp_path / "VERSION").write_text("1.0\n")
    assert new_items.template_problems(tmp_path) == []
