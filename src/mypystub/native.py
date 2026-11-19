"""Native mode on desktop: the real Python tools instead of the mobile ones (#280).

On iOS and Android there's no subprocess and no pip, so MyPyStub resolves and
installs packages itself (``piplike``) and runs prototypes in its own process
(``runner.RunContext``). On a desktop the real tools exist, and Native mode
(one Setup switch, on by default) uses them, so what a prototype does there is
what Python does:

- **One managed venv** for every prototype, in the app's cache, like the
  shared ``site_packages`` folder on a phone. Made on first use from a real
  Python interpreter.
- **pip** installs a prototype's dependencies into it.
- **A subprocess** runs the prototype with the venv's Python. A Toga prototype
  starts its own app and opens its own window. Its output and errors still go
  to the Script tab, and the Script tab's input field writes to its stdin.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import os
import re
import shutil
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path

from .runner import RunTarget

SETTING = "native_mode"  # launcher.toml flag
VENV_FOLDER = "native_venv"
PYTHON_NAME = re.compile(r"python(\d+(\.\d+)?)?(\.exe)?", re.IGNORECASE)


def available(platform: str = sys.platform) -> bool:
    """Whether Native mode can be offered: desktops only."""
    return platform not in ("ios", "android")


def base_python(
    executable: str = sys.executable,
    version: tuple[int, int] = (sys.version_info.major, sys.version_info.minor),
    which: object = shutil.which,
) -> Path | None:
    """A real Python interpreter to make the venv from, or None.

    Under ``briefcase dev`` or ``python -m mypystub`` that's the one running
    the app. A built app's executable is the app itself, not Python, so then
    the same version is looked for on PATH, then any ``python3``.
    """
    if executable and PYTHON_NAME.fullmatch(Path(executable).name):
        return Path(executable)
    major, minor = version
    for name in (f"python{major}.{minor}", f"python{major}", "python"):
        found = which(name)  # type: ignore[operator]
        if found:
            return Path(found)
    return None


def venv_python(venv_dir: Path) -> Path:
    """The Python inside a venv."""
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def ensure_venv(cache_dir: Path, python: Path | None = None) -> Path:
    """The managed venv's Python, making the venv (with pip) the first time.

    Raises RuntimeError when no Python interpreter can be found to make it.
    """
    venv_dir = cache_dir / VENV_FOLDER
    interpreter = venv_python(venv_dir)
    if interpreter.exists():
        return interpreter
    base = python or base_python()
    if base is None:
        raise RuntimeError(
            "Native mode needs a Python interpreter on PATH to make its venv. "
            "Install Python, or turn Native mode off in Setup."
        )
    # Imported here: phones have no venv or subprocess, and never get this far
    if base == Path(sys.executable):
        import venv

        venv.EnvBuilder(with_pip=True, clear=True).create(venv_dir)
    else:
        import subprocess  # another interpreter makes its own: python -m venv

        subprocess.run([str(base), "-m", "venv", "--clear", str(venv_dir)], check=True)
    return interpreter


def pip_command(python: Path, requirements: Sequence[str]) -> list[str]:
    """The pip command that installs `requirements` into `python`'s venv."""
    return [
        str(python),
        "-m",
        "pip",
        "install",
        "--disable-pip-version-check",
        "--progress-bar",
        "off",
        *requirements,
    ]


def run_command(python: Path, target: RunTarget, argv: Sequence[str]) -> list[str]:
    """The command that runs `target` as ``python`` would, with `argv`.

    A script runs as ``python -u script.py``, a module inside a package as
    ``python -u -m pkg.mod`` (so relative imports work), and an entry point
    (``module:function``) the way an installed console script calls it.
    """
    base = [str(python), "-u"]
    if target.reference:
        module, _, attribute = target.reference.partition(":")
        call = (
            "import importlib, sys\n"
            f"sys.argv[0] = {target.argv0 or module!r}\n"
            f"obj = importlib.import_module({module.strip()!r})\n"
            f"for part in {attribute.strip()!r}.split('.'):\n"
            "    obj = getattr(obj, part) if part else obj\n"
            "sys.exit(obj())\n"
        )
        return [*base, "-c", call, *argv]
    if target.module:
        return [*base, "-m", target.module, *argv]
    return [*base, str(target.path), *argv]


def run_environment(
    target: RunTarget,
    overrides: Mapping[str, str | None],
    base: Mapping[str, str] | None = None,
) -> dict[str, str]:
    """The subprocess's environment.

    The launcher's own environment, then the prototype's Setup variables (None
    unsets one), with the prototype's import root on ``PYTHONPATH`` and output
    unbuffered and UTF-8, so it reaches the Script tab as it's written.
    """
    env = dict(os.environ if base is None else base)
    for name, value in overrides.items():
        if value is None:
            env.pop(name, None)
        else:
            env[name] = value
    paths = [str(target.import_root)]
    if existing := env.get("PYTHONPATH"):
        paths.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(paths)
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env
