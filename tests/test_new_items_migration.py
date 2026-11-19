"""A script moves into a project by moving its text, nothing more (#146).

The script's ``main()`` and imports become ``app.py``; its ``# /// script`` keys
(``requires-python``, ``dependencies``) become ``[project]``'s, which both
MyPyStub and Briefcase read. These tests do exactly that and run the result.
"""

import re
import tomllib
from pathlib import Path

import pytest
import tomlkit

from mypystub import new_items, scan
from mypystub.runner import RunContext, target_for

BLOCK = re.compile(r"^# /// script\n((?:#.*\n)*?)^# ///\n", re.MULTILINE)


def script_metadata(source: str) -> dict:
    """The script's PEP 723 block as TOML."""
    match = BLOCK.search(source)
    assert match
    lines = match[1].splitlines(keepends=True)
    return tomllib.loads(
        "".join(line[2:] if line[1:2] == " " else "" for line in lines)
    )


def migrate(script: Path, project: Path) -> None:
    """Move `script` into `project` as a person would, by copying text."""
    source = script.read_text(encoding="utf-8")
    metadata = script_metadata(source)
    module = next((project / "src").iterdir())
    # app.py becomes the script, without its metadata block
    (module / "app.py").write_text(BLOCK.sub("", source), encoding="utf-8")
    # its metadata keys go to [project], unchanged
    pyproject = project / "pyproject.toml"
    document = tomlkit.parse(pyproject.read_text(encoding="utf-8"))
    for key in ("requires-python", "dependencies"):
        document["project"][key] = metadata[key]  # type: ignore[index]
    pyproject.write_text(tomlkit.dumps(document), encoding="utf-8")


@pytest.fixture
def pair(tmp_path: Path) -> tuple[Path, Path]:
    """A new script with a dependency added, and a new project of the same name."""
    script = new_items.create_script(tmp_path, "Tip Split", "Splits a bill")
    text = script.read_text(encoding="utf-8").replace(
        "# dependencies = []", '# dependencies = ["humanize>=4"]'
    )
    script.write_text(text, encoding="utf-8")
    project = new_items.create_project(tmp_path / "projects", "Tip Split")
    return script, project


def test_the_metadata_keys_are_the_same(pair: tuple[Path, Path]) -> None:
    """Every key in the script's block is a [project] key the template has."""
    script, project = pair
    metadata = script_metadata(script.read_text(encoding="utf-8"))
    config = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    assert set(metadata) <= set(config["project"])


def test_dependencies_are_in_one_place(pair: tuple[Path, Path]) -> None:
    """MyPyStub reads [project]; Briefcase adds it to requires (0.4.7, PEP 621)."""
    script, project = pair
    migrate(script, project)
    row = scan.scan_project(project)
    assert row is not None and row["dependencies"] == ["humanize>=4"]
    config = tomllib.loads((project / "pyproject.toml").read_text(encoding="utf-8"))
    app = config["tool"]["briefcase"]["app"]["tip_split"]
    assert not any(r.startswith("humanize") for r in app["requires"])


def test_the_moved_script_runs_as_the_project(
    pair: tuple[Path, Path], capsys, monkeypatch: pytest.MonkeyPatch, request
) -> None:
    """Run the project the way MyPyStub does: the script's output, unchanged."""
    pytest.importorskip("toga_dummy")
    request.getfixturevalue("app")  # in MyPyStub a Toga app is already running
    script, project = pair
    monkeypatch.setattr("builtins.input", lambda prompt="": "Sam")
    with RunContext(target_for(script, script.parent)) as run:
        run.run()
    as_script = capsys.readouterr().out

    migrate(script, project)
    entry = project / "src/tip_split/__main__.py"
    with RunContext(target_for(entry, project / "src")) as run:
        run.run()
    assert (
        capsys.readouterr().out
        == as_script
        == ("Hello from Tip Split!\nNice to meet you, Sam.\n")
    )
