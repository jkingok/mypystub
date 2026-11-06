"""Only pure Python is installed at run time (#172).

iOS can't load code that wasn't signed into the app, and there is no compiler
or ``subprocess`` to build anything with. So a wheel that declares itself
impure, and a source tree that needs a build step, are refused on every
pathway; compiled packages have to be bundled in the app instead.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

# Files that are compiled code, or only exist to build it
COMPILED_SUFFIXES = (".so", ".dylib", ".pyd", ".dll", ".a", ".o", ".framework")
SOURCE_OF_COMPILED = (
    ".c",
    ".cc",
    ".cpp",
    ".cxx",
    ".h",
    ".hpp",
    ".pyx",
    ".pxd",
    ".rs",
    ".f",
    ".f90",
    ".swift",
    ".m",
    ".mm",
)
# Files that say a project is built with a compiler
BUILD_FILES = {"cargo.toml", "cmakelists.txt", "meson.build"}
# Scripts that build backends run, by their conventional names
BUILD_SCRIPTS = ("hatch_build.py", "pdm_build.py")

# Build backends that only package the project's Python files, so installing
# those files is the same as the wheel they would make (#172)
PURE_BACKENDS = frozenset(
    {
        "setuptools.build_meta",
        "setuptools.build_meta:__legacy__",
        "hatchling.build",
        "flit_core.buildapi",
        "pdm.backend",
        "poetry.core.masonry.api",
        "poetry.masonry.api",
        "uv_build",
    }
)
# Build requirements that mean compiled code
COMPILED_REQUIRES = ("maturin", "setuptools-rust", "setuptools_rust", "cython", "cffi")
COMPILED_BACKENDS = ("maturin", "scikit_build_core", "mesonpy", "setuptools_rust")


def wheel_impurity(path: Path) -> str | None:
    """Why the wheel at `path` isn't pure Python, or None if it is.

    Looks at what the wheel says about itself (its tags and ``Root-Is-Purelib``)
    and at what it holds, since a wheel can be tagged ``any`` and still carry a
    binary.
    """
    from packaging.utils import InvalidWheelFilename, parse_wheel_filename

    try:
        _, _, _, tags = parse_wheel_filename(path.name)
    except InvalidWheelFilename:
        tags = frozenset()
    for tag in tags:
        if tag.platform != "any" or tag.abi != "none":
            return f"it is built for {tag} (not pure Python)"
    try:
        with zipfile.ZipFile(path) as wheel:
            names = wheel.namelist()
            for name in names:
                if name.endswith(".dist-info/WHEEL"):
                    text = wheel.read(name).decode("utf-8", "replace")
                    if re.search(
                        r"^Root-Is-Purelib:\s*false\s*$",
                        text,
                        re.IGNORECASE | re.MULTILINE,
                    ):
                        return "it says Root-Is-Purelib: false"
    except zipfile.BadZipFile:
        return None  # a bad archive is reported where it is unpacked
    for name in names:
        lowered = name.lower().rstrip("/")
        if lowered.endswith(COMPILED_SUFFIXES) or ".framework/" in lowered:
            return f"it contains compiled code ({name})"
    return None


def tree_impurity(
    root: Path, project: dict[str, Any], packages: list[Path]
) -> str | None:
    """Why a source tree needs more than copying its Python files, or None.

    `project` is the parsed ``pyproject.toml``; `packages` are the folders and
    modules that would be installed.
    """
    system = project.get("build-system", {})
    backend = str(system.get("build-backend", ""))
    if backend and backend.split(":")[0].split(".")[0] in COMPILED_BACKENDS:
        return f"it is built with {backend}, which compiles code"
    if backend and backend not in PURE_BACKENDS:
        return f"it needs the build backend {backend}, which isn't run here"
    for requirement in system.get("requires", []):
        name = re.split(r"[<>=!~\[; ]", str(requirement).strip(), maxsplit=1)[0].lower()
        if name.replace("_", "-") in {r.replace("_", "-") for r in COMPILED_REQUIRES}:
            return f"it needs {name} to build, which compiles code"
    tool = project.get("tool", {})
    setuptools = tool.get("setuptools", {})
    if setuptools.get("ext-modules") or setuptools.get("cmdclass"):
        return "it builds extension modules or runs its own build commands"
    if tool.get("hatch", {}).get("build", {}).get("hooks"):
        return "it runs build hooks, which can generate files"
    if tool.get("poetry", {}).get("build") or (
        tool.get("pdm", {}).get("build", {}).get("run-setuptools")
    ):
        return "it runs a build script, which can generate files"
    for script in BUILD_SCRIPTS:
        if (root / script).exists():
            return f"it has a {script}, which runs during its build"
    setup = root / "setup.py"
    # Only setuptools runs setup.py: under another backend it's left over
    if setup.exists() and (not backend or backend.startswith("setuptools")):
        config = root / "setup.cfg"
        declarative = config.exists() and "[metadata]" in config.read_text(
            encoding="utf-8", errors="replace"
        )
        if not backend and not declarative:
            return "it has only a setup.py, which would have to run to say what it is"
        text = setup.read_text(encoding="utf-8", errors="replace")
        if re.search(r"ext_modules|Extension\(|cmdclass|cythonize", text):
            return "its setup.py builds extension modules"
        if "install_requires" in text:
            return "its setup.py lists what it needs, so it would have to run"
    folders = [root, *(p for p in packages if p.is_dir())]
    for folder in folders:
        for entry in folder.iterdir():
            if entry.name.lower() in BUILD_FILES:
                return f"it has a {entry.name}, so it is built with a compiler"
    for package in packages:
        files = [package] if package.is_file() else sorted(package.rglob("*"))
        for file in files:
            if not file.is_file():
                continue
            suffix = file.suffix.lower()
            if suffix in COMPILED_SUFFIXES or suffix in SOURCE_OF_COMPILED:
                return f"it contains {file.name}, which is compiled code or needs a compiler"
    return None
