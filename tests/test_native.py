"""Native mode's building blocks: interpreter, venv, pip and run commands (#280)."""

import os
import sys
from pathlib import Path

import pytest

from mypystub import native
from mypystub.runner import RunTarget, entry_target, target_for


def test_offered_on_desktops_only() -> None:
    assert native.available("linux") and native.available("darwin")
    assert native.available("win32")
    assert not native.available("ios") and not native.available("android")


def test_the_running_python_is_used_when_it_is_python() -> None:
    found = native.base_python("/usr/bin/python3.15", (3, 15), lambda name: None)
    assert found == Path("/usr/bin/python3.15")


def test_a_built_app_looks_for_the_same_python_on_path() -> None:
    """A Briefcase app's executable is the app, not Python."""
    seen: list[str] = []

    def which(name: str) -> str | None:
        seen.append(name)
        return "/opt/py/python3" if name == "python3" else None

    found = native.base_python("/Applications/MyPyStub.app/MyPyStub", (3, 15), which)
    assert found == Path("/opt/py/python3")
    assert seen[:2] == ["python3.15", "python3"]


def test_no_python_at_all() -> None:
    assert native.base_python("/app/MyPyStub", (3, 15), lambda name: None) is None


def test_ensure_venv_reuses_one_already_made(tmp_path: Path) -> None:
    python = native.venv_python(tmp_path / native.VENV_FOLDER)
    python.parent.mkdir(parents=True)
    python.write_text("")
    assert native.ensure_venv(tmp_path, python=Path("/nowhere")) == python


def test_ensure_venv_without_python_says_how_to_fix_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(native, "base_python", lambda: None)
    with pytest.raises(RuntimeError, match="Native mode off"):
        native.ensure_venv(tmp_path)


def test_pip_installs_the_requirements() -> None:
    command = native.pip_command(Path("py"), ["humanize>=4", "rich"])
    assert command[:4] == ["py", "-m", "pip", "install"]
    assert command[-2:] == ["humanize>=4", "rich"]


def test_a_script_runs_as_a_script(tmp_path: Path) -> None:
    script = tmp_path / "tool.py"
    script.write_text("")
    command = native.run_command(Path("py"), target_for(script, tmp_path), ["a"])
    assert command == ["py", "-u", str(script), "a"]


def test_a_package_module_runs_with_dash_m(tmp_path: Path) -> None:
    package = tmp_path / "src" / "pkg"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "__main__.py").write_text("")
    target = target_for(package / "__main__.py", tmp_path / "src")
    assert native.run_command(Path("py"), target, []) == ["py", "-u", "-m", "pkg"]


def test_an_entry_point_is_called_like_a_console_script(tmp_path: Path) -> None:
    (tmp_path / "pyproject.toml").write_text("")
    target = entry_target("tool", "pkg.cli:main", "console", tmp_path, tmp_path)
    command = native.run_command(Path("py"), target, ["x"])
    assert command[:3] == ["py", "-u", "-c"] and command[-1] == "x"
    assert "import_module('pkg.cli')" in command[3] and "'main'" in command[3]


def test_the_entry_point_code_runs(tmp_path: Path) -> None:
    """The generated -c code really calls the function and exits with it."""
    import subprocess

    (tmp_path / "cli.py").write_text(
        "import sys\ndef main():\n    print(sys.argv)\n    return 3\n"
    )
    (tmp_path / "pyproject.toml").write_text("")
    target = entry_target("tool", "cli:main", "console", tmp_path, tmp_path)
    done = subprocess.run(
        native.run_command(Path(sys.executable), target, ["x"]),
        env=native.run_environment(target, {}),
        capture_output=True,
        text=True,
        check=False,
    )
    assert done.returncode == 3 and done.stdout.strip() == "['tool', 'x']"


def test_the_environment(tmp_path: Path) -> None:
    target = RunTarget(tmp_path / "a.py", tmp_path / "src", tmp_path)
    base = {"HOME": "/h", "DROP": "1", "PYTHONPATH": "/existing"}
    env = native.run_environment(target, {"NEW": "2", "DROP": None}, base)
    assert env["HOME"] == "/h" and env["NEW"] == "2" and "DROP" not in env
    assert env["PYTHONPATH"] == os.pathsep.join([str(tmp_path / "src"), "/existing"])
    assert env["PYTHONUNBUFFERED"] == "1" and env["PYTHONIOENCODING"] == "utf-8"
