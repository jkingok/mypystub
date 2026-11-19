"""New items: the details screen's fields, and what a project carries (#146).

Description, bundle and author go into the templates; Android's Back and
documents provider, the icons, and input() come with every new project.
"""

import threading
import tomllib
from pathlib import Path

import pytest

from mypystub import new_items


def test_a_script_takes_a_description(tmp_path: Path) -> None:
    text = new_items.create_script(tmp_path, "My Tool", 'Counts "things"').read_text()
    assert text.startswith('"""My Tool: Counts \'things\'"""')


def test_a_script_without_one_says_what_to_write(tmp_path: Path) -> None:
    text = new_items.create_script(tmp_path, "My Tool").read_text()
    assert "My Tool: One line about what it does" in text


def test_a_project_takes_its_details(tmp_path: Path) -> None:
    project = new_items.create_project(
        tmp_path, "Weather Now", "Shows the weather", "au.id.someone", "Sam Coder"
    )
    config = tomllib.loads((project / "pyproject.toml").read_text())
    assert config["project"]["description"] == "Shows the weather"
    assert config["project"]["authors"] == [{"name": "Sam Coder"}]
    assert config["tool"]["briefcase"]["bundle"] == "au.id.someone"
    bootstrap = (project / "src/weather_now/bootstrap.py").read_text()
    assert 'APP_ID = "au.id.someone.weather_now"' in bootstrap


def test_blank_details_keep_working_defaults(tmp_path: Path) -> None:
    project = new_items.create_project(tmp_path, "Weather Now")
    config = tomllib.loads((project / "pyproject.toml").read_text())
    assert config["project"]["description"] == "Weather Now, a Toga app"
    assert config["tool"]["briefcase"]["bundle"] == "com.example"


@pytest.mark.parametrize("bundle", ["example", "com.", "com example", "1com.x"])
def test_a_bad_bundle_is_refused_before_anything_is_made(
    tmp_path: Path, bundle: str
) -> None:
    with pytest.raises(new_items.NameProblem):
        new_items.create_project(tmp_path, "Weather Now", bundle=bundle)
    assert list(tmp_path.iterdir()) == []


def test_dependencies_are_left_as_todos(tmp_path: Path) -> None:
    project = new_items.create_project(tmp_path, "Weather Now")
    assert "TODO: add the packages" in (project / "pyproject.toml").read_text()
    script = new_items.create_script(tmp_path, "My Tool").read_text()
    assert "TODO: add the packages" in script


def test_android_java_is_renamed_with_the_project(tmp_path: Path) -> None:
    project = new_items.create_project(tmp_path, "Weather Now")
    java = project / "android/java/weather_now/android"
    for name in ("AppDocumentsProvider.java", "PyBackCallback.java"):
        assert (java / name).read_text().startswith("package weather_now.android;")
    config = tomllib.loads((project / "pyproject.toml").read_text())
    android = config["tool"]["briefcase"]["app"]["weather_now"]["android"]
    assert (
        "weather_now.android.AppDocumentsProvider"
        in (android["android_manifest_application_extra_content"])
    )
    assert "/android/java" in android["build_gradle_extra_content"]
    back = (project / "src/weather_now/android_back.py").read_text()
    assert '"weather_now.android.PyBackCallback"' in back


def test_icons_come_with_the_project(tmp_path: Path) -> None:
    project = new_items.create_project(tmp_path, "Weather Now")
    assert (project / "assets/src_icon.png").read_bytes().startswith(b"\x89PNG")
    assert (project / "generate_icons.py").exists()
    config = tomllib.loads((project / "pyproject.toml").read_text())
    app = config["tool"]["briefcase"]["app"]["weather_now"]
    assert app["icon"] == "assets/icons/png/icon-512"
    assert app["iOS"]["icon"] == "assets/icons/ios/icon"
    assert app["android"]["icon"] == "assets/icons/android/icon"
    assert "/assets/icons" in (project / ".gitignore").read_text()


def test_the_template_icons_script_is_the_launchers() -> None:
    """generate_icons.py is a link to the launcher's, so there's one to maintain."""
    root = Path(__file__).parent.parent
    template = new_items.PROJECT_TEMPLATE / "generate_icons.py"
    assert template.resolve() == (root / "generate_icons.py").resolve()


def test_input_from_main_on_the_main_thread_is_refused() -> None:
    """Waiting there would freeze the app, so it raises instead."""
    toga = pytest.importorskip("toga")
    pytest.importorskip("toga_dummy")
    import importlib.util

    path = new_items.PROJECT_TEMPLATE / "src/app_template/script_view.py"
    spec = importlib.util.spec_from_file_location("script_view_t", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert threading.current_thread() is threading.main_thread()
    view = module.ScriptView.__new__(module.ScriptView)
    view._given = threading.Event()
    with pytest.raises(RuntimeError, match="main thread"):
        view.ask("Name? ")
    assert toga  # imported for the module under test
