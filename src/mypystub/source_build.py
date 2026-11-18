"""Build a wheel from a source tree with the project's own backend (#257).

Every common build backend (setuptools, hatchling, flit-core, poetry-core) is
pure Python, so it can be installed at run time like any pure package and its
PEP 517 ``build_wheel`` hook called **in this process**: there is no
``subprocess`` on iOS. The wheel is then checked for purity and installed like
one from PyPI, so nothing here writes ``.dist-info`` by hand.

A build runs inside a snapshot of the process state (modules, ``sys.path``,
working folder, environment, argv), restored afterwards, with every module the
backend imported dropped, so the launcher never imports from the backend's
folder. Starting a process is blocked for the length of the build, on every
platform, so a build that would need one (a compiler, ``git``) fails the same
way everywhere. Backends report failures by raising, and setuptools by
``SystemExit``, so both are caught and reported as one :class:`BuildProblem`.

Only the source of a requirement's URL is built here. Projects the user runs
are never built: they run from their folder. And Briefcase isn't a build
backend at all: a project made with it builds with the backend its
``[build-system]`` names (setuptools when it names none).

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import importlib
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# What pip assumes for a project with no [build-system] (PEP 517, PEP 518)
DEFAULT_REQUIRES = ("setuptools>=40.8.0",)
DEFAULT_BACKEND = "setuptools.build_meta:__legacy__"
# Version plugins that read Git, and the variables that give them a version
VERSION_VARIABLES = ("SETUPTOOLS_SCM_PRETEND_VERSION", "HATCH_VCS_PRETEND_VERSION")


class BuildProblem(Exception):
    """A source tree that can't be built here; the message says why."""


@dataclass(frozen=True)
class BuildSystem:
    """A project's ``[build-system]``: what to install, and what to call."""

    requires: tuple[str, ...]
    backend: str  # "module" or "module:object"
    backend_path: tuple[str, ...] = ()  # in-tree backends, relative to the root


def build_system(root: Path) -> BuildSystem:
    """Read `root`'s ``[build-system]``, with pip's defaults where it has none."""
    path = root / "pyproject.toml"
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except (OSError, ValueError) as error:
        raise BuildProblem(f"its pyproject.toml can't be read: {error}") from None
    table = data.get("build-system", {})
    if not isinstance(table, Mapping):
        table = {}
    backend = table.get("build-backend")
    requires = table.get("requires")
    if not isinstance(backend, str) or not backend:
        return BuildSystem(
            tuple(requires) if isinstance(requires, list) else DEFAULT_REQUIRES,
            DEFAULT_BACKEND,
        )
    paths = table.get("backend-path", [])
    return BuildSystem(
        tuple(str(r) for r in requires) if isinstance(requires, list) else (),
        backend,
        tuple(str(p) for p in paths) if isinstance(paths, list) else (),
    )


def _no_process(*args: Any, **kwargs: Any) -> Any:
    raise OSError("starting a process isn't possible here")


@contextmanager
def isolated(paths: list[Path], cwd: Path, env: Mapping[str, str]) -> Iterator[None]:
    """Process state for one build, put back afterwards; processes blocked.

    `paths` go first on ``sys.path``. Modules first imported during the build
    are dropped afterwards, so the backend can't linger in ``sys.modules``.
    """
    saved_modules = set(sys.modules)
    saved_path = list(sys.path)
    saved_meta = list(sys.meta_path)
    saved_argv = list(sys.argv)
    saved_env = dict(os.environ)
    saved_cwd = os.getcwd()
    blocked: list[tuple[Any, str, Any]] = [
        (subprocess, "Popen", subprocess.Popen),
        (os, "system", os.system),
    ]
    for name in ("posix_spawn", "posix_spawnp", "fork", "execv", "execve"):
        if hasattr(os, name):
            blocked.append((os, name, getattr(os, name)))
    try:
        for owner, name, _ in blocked:
            setattr(owner, name, _no_process)
        sys.path[:0] = [str(p) for p in paths]
        os.environ.update(env)
        os.chdir(cwd)
        yield
    finally:
        for owner, name, original in blocked:
            setattr(owner, name, original)
        os.chdir(saved_cwd)
        os.environ.clear()
        os.environ.update(saved_env)
        sys.argv[:] = saved_argv
        sys.meta_path[:] = saved_meta
        sys.path[:] = saved_path
        for name in set(sys.modules) - saved_modules:
            del sys.modules[name]
        importlib.invalidate_caches()


def _backend_hooks(spec: str) -> Any:
    module_name, _, attribute = spec.partition(":")
    hooks: Any = importlib.import_module(module_name)
    for part in filter(None, attribute.split(".")):
        hooks = getattr(hooks, part)
    return hooks


def build_wheel(
    root: Path,
    backend_site: Path,
    wheel_dir: Path,
    version: str | None = None,
    system: BuildSystem | None = None,
) -> Path:
    """Build `root` into a wheel in `wheel_dir` with its backend; the wheel's path.

    The backend (and what it requires) must already be installed in
    `backend_site`. The source is copied first, as some backends write into
    the tree (setuptools' ``build`` and ``*.egg-info``). `version` is handed to
    version plugins that would otherwise ask Git.
    """
    system = system or build_system(root)
    wheel_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mypystub_build_") as scratch:
        tree = Path(scratch) / root.name
        shutil.copytree(root, tree, symlinks=True)
        in_tree = [(tree / p).resolve() for p in system.backend_path]
        if any(not p.is_relative_to(tree.resolve()) for p in in_tree):
            raise BuildProblem("its build backend path leaves the project")
        env = {name: version for name in VERSION_VARIABLES} if version else {}
        try:
            with isolated([*in_tree, backend_site], tree, env):
                hooks = _backend_hooks(system.backend)
                name = hooks.build_wheel(str(wheel_dir))
        except (Exception, SystemExit) as error:  # noqa: BLE001  (see module doc)
            detail = str(error).strip().splitlines()
            reason = detail[-1] if detail else type(error).__name__
            raise BuildProblem(
                f"it needs a build step that can't run here ({reason[:200]})"
            ) from None
    wheel = wheel_dir / str(name)
    if not wheel.is_file() or wheel.suffix != ".whl":
        raise BuildProblem(f"its build backend made no wheel ({name})")
    return wheel


BackendInstaller = Callable[[tuple[str, ...], Path], None]
