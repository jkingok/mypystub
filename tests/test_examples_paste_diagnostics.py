"""The paste_diagnostics example: what it says Paste would do with a clipboard."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

EXAMPLE = (
    Path(__file__).parent.parent
    / "src"
    / "mypystub"
    / "resources"
    / "examples"
    / "hardware"
    / "paste_diagnostics.py"
)


@pytest.fixture
def diagnostics() -> ModuleType:
    """The example as a module (it only reads a clipboard when run on a device)."""
    spec = importlib.util.spec_from_file_location("paste_diagnostics", EXAMPLE)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_android_text_is_treated_as_python(diagnostics: ModuleType) -> None:
    """Copied text with nothing else is saved as a script, and asks for a name."""
    said = diagnostics.android_verdict({"text": True, "files": []}, True, True)
    assert said == "Paste would treat the text as Python, and ask for a file name."


def test_android_files_name_what_would_be_imported(diagnostics: ModuleType) -> None:
    """Every readable copied file is named, and a file beats text."""
    files = [{"name": "a.py", "read": 3}, {"name": "b.zip", "read": 9}]
    said = diagnostics.android_verdict({"text": True, "files": files}, True, True)
    assert said == "Paste would import a.py, b.zip."


def test_android_unreadable_file_is_reported_with_its_error(
    diagnostics: ModuleType,
) -> None:
    """A URI the clipboard didn't grant fails with the exception shown."""
    file = {"exception": "SecurityException('no grant')"}
    said = diagnostics.android_verdict({"files": [file]}, True, True)
    assert "fail to read" in said and "SecurityException" in said


def test_android_empty_zero_byte_and_unwritable(diagnostics: ModuleType) -> None:
    """Nothing copied, something unreadable, an empty file, and no write access."""
    verdict = diagnostics.android_verdict
    assert "empty" in verdict({}, False, True)
    assert "nothing could be read" in verdict({"text": False, "files": []}, True, True)
    assert "fail to read" in verdict({"files": [{"name": "x", "read": 0}]}, True, True)
    assert "isn't writable" in verdict({}, True, False)


def test_other_platforms_say_where_it_runs(
    diagnostics: ModuleType, capsys: pytest.CaptureFixture[str]
) -> None:
    """On desktop it prints a short note instead of failing on a missing API."""
    diagnostics.main()
    assert "only runs there" in capsys.readouterr().out
