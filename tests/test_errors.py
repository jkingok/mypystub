"""Errors in handlers must reach a dialog, not just the log."""

import ast
import asyncio
from pathlib import Path
from typing import Any

import pytest

from mypystub.errors import guarded

SRC = Path(__file__).parent.parent / "src" / "mypystub"
HANDLER_KEYWORDS = ("on_",)
HANDLER_SUFFIXES = ("_action",)


class Owner:
    """Something with a handler and somewhere to report its errors."""

    def __init__(self) -> None:
        self.reported: list[tuple[str, str]] = []

    async def report_error(self, error: Exception, where: str) -> None:
        self.reported.append((str(error), where))

    @guarded
    async def press_async(self, widget: Any = None) -> str:
        raise ValueError("boom")

    @guarded
    def press_sync(self, widget: Any = None) -> str:
        raise ValueError("bang")

    @guarded
    def fine(self) -> str:
        return "ok"


def test_async_handler_error_is_reported() -> None:
    """An async handler's exception is shown, and does not escape."""
    owner = Owner()
    asyncio.run(owner.press_async())
    assert owner.reported == [("boom", "press async")]


def test_sync_handler_error_is_reported() -> None:
    """A plain handler's exception is shown too."""

    async def go() -> Owner:
        owner = Owner()
        owner.press_sync()
        await asyncio.sleep(0)
        return owner

    assert asyncio.run(go()).reported == [("bang", "press sync")]


def test_handler_results_pass_through() -> None:
    """A handler that works behaves as before."""
    assert Owner().fine() == "ok"


def test_failing_report_does_not_raise(capsys: pytest.CaptureFixture[str]) -> None:
    """If the dialog itself fails, the error is only logged."""

    class Broken(Owner):
        async def report_error(self, error: Exception, where: str) -> None:
            raise RuntimeError("no dialog")

    asyncio.run(Broken().press_async())
    assert "no dialog" in capsys.readouterr().err


def handler_names() -> set[tuple[str, str]]:
    """(file, method) for each ``self.method`` passed as a Toga handler keyword."""
    found: set[tuple[str, str]] = set()
    for path in SRC.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.keyword) or node.arg is None:
                continue
            if not node.arg.startswith(HANDLER_KEYWORDS) and not node.arg.endswith(
                HANDLER_SUFFIXES
            ):
                continue
            value = node.value
            if (
                isinstance(value, ast.Attribute)
                and isinstance(value.value, ast.Name)
                and value.value.id == "self"
            ):
                found.add((path.name, value.attr))
    return found


def test_every_launcher_handler_is_guarded() -> None:
    """Every method wired as a handler shows its errors (Toga only logs them)."""
    from mypystub import run_backups, run_with, ui

    # Toga's own plumbing, or handlers that cannot fail in a way worth a dialog
    exempt = {"close_keyboard", "swap_in"}  # swap_in: a widget's own
    missing = []
    for file, name in sorted(handler_names()):
        if name in exempt:
            continue
        for cls in (ui.Prototype, run_with.RunWithForm, run_backups.BackupsSection):
            method = getattr(cls, name, None)
            if method is not None:
                break
        else:
            missing.append(f"{file}: {name} (not found)")
            continue
        if not getattr(method, "__guarded__", False):
            missing.append(f"{file}: {name}")
    assert not missing, "handlers that would bury errors: " + ", ".join(missing)
