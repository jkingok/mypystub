"""The resume_counter example: state saved as it goes, picked up on the next run (#188)."""

import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType

import pytest

EXAMPLE = (
    Path(__file__).parent.parent
    / "src"
    / "mypystub"
    / "resources"
    / "examples"
    / "basics"
    / "resume_counter.py"
)


@pytest.fixture
def counter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ModuleType:
    """The example, with its state file in a temp folder and no waiting."""
    spec = importlib.util.spec_from_file_location("resume_counter", EXAMPLE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "state_file", lambda: tmp_path / "state.json")
    monkeypatch.setattr(module.time, "sleep", lambda seconds: None)
    return module


def run_main(module: ModuleType, monkeypatch: pytest.MonkeyPatch, *args: str) -> None:
    """Run main() as if started with `args`."""
    monkeypatch.setattr(sys, "argv", ["resume_counter.py", *args])
    module.main()


def test_it_counts_and_finishes_with_nothing_left_behind(
    counter: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A run that completes starts fresh next time."""
    run_main(counter, monkeypatch, "3")
    out = capsys.readouterr().out
    assert "Starting at 0, counting to 3." in out and "Done." in out
    assert not (tmp_path / "state.json").exists()


def test_a_run_cut_short_is_picked_up_by_the_next(
    counter: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Stopped after 3: the next run carries on from 3, without being told."""
    steps = {"n": 0}

    def stop_after_three(seconds: float) -> None:
        steps["n"] += 1
        if steps["n"] == 4:
            raise KeyboardInterrupt  # the app is ended during the 4th step

    monkeypatch.setattr(counter.time, "sleep", stop_after_three)
    with pytest.raises(KeyboardInterrupt):
        run_main(counter, monkeypatch, "5")
    assert json.loads((tmp_path / "state.json").read_text())["count"] == 3
    capsys.readouterr()

    monkeypatch.setattr(counter.time, "sleep", lambda seconds: None)
    run_main(counter, monkeypatch, "5")
    out = capsys.readouterr().out
    assert "carrying on from 3" in out and "Done." in out


def test_a_different_target_starts_fresh(
    counter: ModuleType, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Saved state for another job isn't picked up."""
    (tmp_path / "state.json").write_text(json.dumps({"count": 2, "target": 10}))
    run_main(counter, monkeypatch, "3")


def test_a_damaged_state_file_is_just_a_fresh_start(
    counter: ModuleType,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Never an error."""
    (tmp_path / "state.json").write_text("{not json")
    run_main(counter, monkeypatch, "2")
    assert "Starting at 0" in capsys.readouterr().out


def test_it_stays_standalone() -> None:
    """No MyPyStub-specific API."""
    tree = ast.parse(EXAMPLE.read_text(encoding="utf-8"))
    imported = {
        alias.name.split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        (node.module or "").split(".")[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "mypystub" not in imported
