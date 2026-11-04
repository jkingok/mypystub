"""Pasting files copied in the Files app, and the Paste diagnostics example."""

import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest

import mypystub
from mypystub import paste_import

FILE = "com.apple.DocumentManager.FINode.File"
LOCATION = "com.apple.DocumentManager.FINode.Location"
ACTIVITY = "com.apple.uikit.useractivity"
PYZ = "dyn.ah62d4rv4ge81a8p4"

# (registered types, has text, what to read), as seen from Files on iOS 27
CASES = [
    ([FILE, "public.zip-archive"], False, "public.zip-archive"),
    ([FILE, "public.python-script"], True, "public.python-script"),
    ([FILE, PYZ], False, PYZ),
    (["public.utf8-plain-text"], True, None),
    (["public.jpeg"], False, "public.jpeg"),
    ([FILE], False, None),
    ([], False, None),
]


def diagnostics() -> ModuleType:
    """The bundled example, loaded as a module without running it."""
    path = Path(mypystub.__file__).parent / "resources" / "examples"
    path = path / "hardware" / "paste_diagnostics.py"
    spec = importlib.util.spec_from_file_location("paste_diagnostics", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(("types", "has_text", "expected"), CASES)
def test_file_type_skips_bookmarks_and_keeps_text(
    types: list[str], has_text: bool, expected: str | None
) -> None:
    """The real file's type is chosen, not the Files app's bookmark listed first."""
    assert paste_import.file_type(types, has_text) == expected


@pytest.mark.parametrize(("types", "has_text", "expected"), CASES)
def test_diagnostics_chooses_the_type_paste_does(
    types: list[str], has_text: bool, expected: str | None
) -> None:
    """The example can't import the app, so its copy of the rule is checked here."""
    assert diagnostics().file_type(types, has_text) == expected


def test_a_folder_is_recognised() -> None:
    """A copied folder is told apart, and neither rule reads it as a file."""
    types = [LOCATION, ACTIVITY, "public.folder"]
    assert paste_import.is_folder(types)
    assert not paste_import.is_folder([FILE, "public.zip-archive"])
    assert diagnostics().file_type(types, False) is None


def test_keep_copy_replaces_the_last_paste(tmp_path: Path) -> None:
    """The copy keeps its name, and only the latest paste is kept."""
    source = tmp_path / "source"
    source.mkdir()
    (source / "first.zip").write_text("one")
    (source / "second.py").write_text("two")
    folder = tmp_path / "cache" / "paste"
    first = paste_import.keep_copy(source / "first.zip", folder)
    assert first == folder / "first.zip"
    assert first.read_text() == "one"
    second = paste_import.keep_copy(source / "second.py", folder)
    assert second.read_text() == "two"
    assert [path.name for path in folder.iterdir()] == ["second.py"]


def test_dynamic_types_are_decoded() -> None:
    """A dynamic type shows what it stands for; others are left alone."""
    assert "pyz" in diagnostics().decode_dyn_uti(PYZ)
    assert diagnostics().decode_dyn_uti("public.zip-archive") == "public.zip-archive"
    assert diagnostics().decode_dyn_uti("dyn.a!!") == "dyn.a!!"


def test_sniff_tells_formats_apart(tmp_path: Path) -> None:
    """The report says what bytes are, whatever the name claims."""
    sniff: Any = diagnostics().sniff
    fake = tmp_path / "fake.zip"
    fake.write_bytes(b"bplist00\x00\x01")
    assert "plist" in sniff(fake)
    text = tmp_path / "hello.py"
    text.write_text("print(1)\n")
    assert "print(1)" in sniff(text)
    assert sniff(tmp_path) == "a folder"


def test_diagnostics_verdicts() -> None:
    """Each outcome says what Paste would do, and what to try if it can't."""
    verdict: Any = diagnostics().verdict
    nothing = {"url": False, "text": False}
    assert "empty" in verdict(nothing, 0, True)
    assert "Allow Paste" in verdict(nothing, 1, True)
    assert "writable" in verdict(nothing, 1, False)
    assert "can't be pasted" in verdict(nothing | {"folder": True}, 1, True)
    file = {"file": {"name": "a.zip", "size": 3}}
    assert "import a.zip" in verdict(nothing | file, 1, True)
    failed = {"file": {"error": "nope"}}
    assert "nope" in verdict(nothing | failed, 1, True)
