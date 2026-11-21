"""togax_jkingok imports without error as every Toga platform (#323).

iOS and Android are its primary platforms and the desktops work; web and
Textual may do little, but importing must never fail. Each import runs in a
fresh interpreter that, once Toga itself is imported, reports the platform's
``sys.platform`` and refuses
every backend's native libraries, so a module-level import that isn't behind
a platform check fails here.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

import togax_jkingok

PACKAGE = Path(togax_jkingok.__file__).parent
SRC = PACKAGE.parent
# sys.platform as each Toga backend sees it (web runs on Pyodide: emscripten;
# Textual runs in a terminal on any of the others)
PLATFORMS = ["ios", "android", "darwin", "linux", "win32", "emscripten"]
NATIVE = ["toga_iOS", "toga_android", "toga_cocoa", "toga_gtk", "toga_winforms"]
NATIVE += ["toga_web", "toga_textual", "rubicon", "java", "android", "gi", "clr"]

IMPORT_AS = """
import importlib, importlib.abc, json, pkgutil, sys

class Refuse(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in NATIVE:
            raise ImportError(f"{name} isn't available here")
        return None

NATIVE = set(json.loads(sys.argv[2]))
# Toga and the standard library are imported for real first: faking win32 on
# Linux would break asyncio itself, and their platform handling isn't ours
import asyncio, toga, toga.handlers, toga.style.applicator
sys.meta_path.insert(0, Refuse())
sys.platform = sys.argv[1]
import togax_jkingok
for module in pkgutil.iter_modules(togax_jkingok.__path__):
    importlib.import_module(f"togax_jkingok.{module.name}")
"""


@pytest.mark.parametrize("platform", PLATFORMS)
def test_every_module_imports_as(platform: str) -> None:
    result = subprocess.run(
        [sys.executable, "-c", IMPORT_AS, platform, json.dumps(NATIVE)],
        capture_output=True,
        text=True,
        cwd=SRC,
        env={"PYTHONPATH": str(SRC), "TOGA_BACKEND": "toga_dummy"},
        check=False,
    )
    assert result.returncode == 0, result.stderr
