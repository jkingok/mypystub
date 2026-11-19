"""The script and project templates, and making new items from them (#146)."""

import ast
import tomllib
from pathlib import Path

import pytest

from mypystub import new_items, scan
from mypystub.runner import RunContext, target_for


@pytest.mark.parametrize(
    ("typed", "module"),
    [("My Tool", "my_tool"), (" weather  now! ", "weather_now"), ("2048", "app_2048")],
)
def test_module_names(typed: str, module: str) -> None:
    assert new_items.module_name(typed) == module


def test_an_empty_name_is_refused() -> None:
    with pytest.raises(new_items.NameProblem):
        new_items.module_name("  !! ")


def test_a_script_is_made_and_runs(
    tmp_path: Path, capsys, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("builtins.input", lambda prompt="": "Sam")
    path = new_items.create_script(tmp_path, "My Tool")
    assert path.name == "my_tool.py"
    text = path.read_text()
    assert "Script Template" not in text and "My Tool" in text
    row = scan.scan_script(path)
    assert row is not None and row["dependencies"] == []
    assert row["subtitle"].startswith("My Tool:")
    with RunContext(target_for(path, tmp_path)) as run:
        run.run()
    assert capsys.readouterr().out == "Hello from My Tool!\nNice to meet you, Sam.\n"


def test_a_name_never_replaces_what_is_there(tmp_path: Path) -> None:
    first = new_items.create_script(tmp_path, "tool")
    second = new_items.create_script(tmp_path, "tool")
    assert first != second and second.name == "tool_2.py"
    a = new_items.create_project(tmp_path, "app")
    b = new_items.create_project(tmp_path, "app")
    assert b.name == "app_2" and (b / "src" / "app_2" / "app.py").exists()
    assert "app_2.bootstrap" in (b / "src" / "app_2" / "__main__.py").read_text()
    assert a.exists()


def test_a_project_has_every_placeholder_replaced(tmp_path: Path) -> None:
    project = new_items.create_project(tmp_path, "Weather Now")
    texts = [
        p.read_text()
        for p in project.rglob("*")
        if p.is_file() and p.suffix in new_items.TEXT_SUFFIXES
    ]
    for leftover in ("app_template", "App Template", "app-template"):
        assert not any(leftover in t for t in texts), leftover
    assert not any("app_template" in str(p) for p in project.rglob("*"))
    for py in project.rglob("*.py"):
        ast.parse(py.read_text())  # still valid Python


def test_a_project_is_a_briefcase_project(tmp_path: Path) -> None:
    """What Briefcase needs to build it, for every platform, as it is."""
    project = new_items.create_project(tmp_path, "Weather Now")
    data = tomllib.loads((project / "pyproject.toml").read_text())
    assert data["project"]["name"] == "weather-now"
    app = data["tool"]["briefcase"]["app"]["weather_now"]
    assert app["formal_name"] == "Weather Now"
    assert app["sources"] == ["src/weather_now"]
    for platform in ("macOS", "linux", "windows", "iOS", "android"):
        assert app[platform]["requires"], platform
    assert app["iOS"]["info"]["UIFileSharingEnabled"] is True


def test_the_projects_permissions_match_the_launchers(tmp_path: Path) -> None:
    """What works in MyPyStub should work as an app of its own."""
    ours = tomllib.loads(
        (Path(__file__).resolve().parent.parent / "pyproject.toml").read_text()
    )["tool"]["briefcase"]["app"]["mypystub"]
    project = new_items.create_project(tmp_path, "Weather Now")
    app = tomllib.loads((project / "pyproject.toml").read_text())["tool"]["briefcase"][
        "app"
    ]["weather_now"]
    assert set(app["permission"]) == set(ours["permission"])
    for key in ("UIFileSharingEnabled", "LSSupportsOpeningDocumentsInPlace"):
        assert app["iOS"]["info"][key] == ours["iOS"]["info"][key]


def test_a_project_scans_as_one_runnable_project(tmp_path: Path) -> None:
    new_items.create_project(tmp_path, "Weather Now")
    (row,) = scan.scan_all_prototypes(tmp_path)
    assert row["kind"] == "project"
    assert row["title"] == "Weather Now"
    assert Path(row["entry_point"]).name == "__main__.py"
