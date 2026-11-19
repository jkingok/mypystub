"""scripts/check_template_links.py: stop a build from a clone without links."""

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "check_template_links.py"
TEMPLATE = ROOT / "src" / "mypystub" / "resources" / "templates" / "project"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(), reason="scripts/ is not bundled on device"
)


def load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_template_links", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_this_checkout_passes() -> None:
    done = subprocess.run(
        [sys.executable, str(SCRIPT)], check=False, capture_output=True
    )
    assert done.returncode == 0 and not done.stderr


def test_a_clone_without_links_fails_and_says_why(tmp_path: Path, capsys) -> None:
    damaged = tmp_path / "project"
    shutil.copytree(TEMPLATE, damaged, symlinks=True)
    links = [p for p in damaged.rglob("*") if p.is_symlink()]
    assert links  # the template does have some
    for link in links:
        target = str(link.readlink())
        link.unlink()
        link.write_text(target)  # what git writes when it can't make a link
    assert load().main(damaged) == 1
    err = capsys.readouterr().err
    assert "core.symlinks" in err and "generate_icons.py" in err


def test_it_needs_only_the_standard_library() -> None:
    """It runs before anything is installed: python -I, from anywhere."""
    done = subprocess.run(
        [sys.executable, "-I", str(SCRIPT)], check=False, cwd="/", capture_output=True
    )
    assert done.returncode == 0


def test_both_builds_run_it_first() -> None:
    fastfile = (ROOT / "fastlane" / "Fastfile").read_text()
    for check in (
        "def check_android_env",
        "def check_android_signing_env",
        "def check_ios_env",
    ):
        body = fastfile[fastfile.index(check) :]
        assert body.splitlines()[1].strip() == "check_template_links"
    build = (ROOT / "scripts" / "build_android.py").read_text()
    main = build[build.index("def main(") :]
    assert main.index("check_template_links.py") < main.index("overrides(")
