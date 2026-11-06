"""What a source tree says about itself, read without running anything (#172).

A wheel's METADATA is written by a build, which can't run here. Most projects
declare the same facts in a file, in one of three formats: ``[project]`` in
``pyproject.toml``, Poetry's ``[tool.poetry]``, or ``setup.cfg``. This reads
each into the shape of ``[project]``, and finds the package folders and version
those formats point at. Python files are only ever searched as text.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import configparser
import re
import tomllib
from pathlib import Path
from typing import Any

# ``__version__ = "1.2"`` and the like, at the start of a line
VERSION_LINE = re.compile(
    r"^(?:__version__|VERSION|version)\s*(?::\s*\w+\s*)?=\s*[\"']([^\"']+)[\"']",
    re.MULTILINE,
)
POETRY_SOURCES = ("git", "path", "url", "file")


class SourceProblem(Exception):
    """A source archive that can't be installed; the message says why."""


def read_pyproject(root: Path) -> dict[str, Any]:
    """The parsed ``pyproject.toml`` at `root`, or ``{}`` if there isn't one."""
    path = root / "pyproject.toml"
    if not path.is_file():
        return {}
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (tomllib.TOMLDecodeError, UnicodeDecodeError) as error:
        raise SourceProblem(f"its pyproject.toml can't be read: {error}") from None


def declared_project(root: Path, data: dict[str, Any]) -> dict[str, Any]:
    """The project's metadata in the shape of ``[project]``, whichever format."""
    project = data.get("project")
    if isinstance(project, dict) and project.get("name"):
        return project
    poetry = data.get("tool", {}).get("poetry", {})
    if poetry.get("name"):
        return _from_poetry(poetry)
    config = _setup_cfg(root)
    if config is not None and config.get("metadata", "name", fallback=""):
        return _from_setup_cfg(config)
    if not data:
        raise SourceProblem(
            "it has no pyproject.toml, so what it is can't be read without running "
            "a build"
        )
    raise SourceProblem("its pyproject.toml has no [project] name")


# -- Poetry ---------------------------------------------------------------


def _release(version: str) -> list[int]:
    found = re.match(r"\d+(?:\.\d+)*", version)
    return [int(n) for n in found.group().split(".")] if found else [0]


def _padded(numbers: list[int], length: int) -> str:
    return ".".join(str(n) for n in numbers + [0] * (length - len(numbers)))


def _caret(version: str) -> str:
    """``^1.2`` allows changes that keep the first non-zero number."""
    numbers = _release(version)
    place = next((i for i, n in enumerate(numbers) if n), len(numbers) - 1)
    upper = [*numbers[:place], numbers[place] + 1]
    return f">={version},<{_padded(upper, len(numbers))}"


def _tilde(version: str) -> str:
    """``~1.2.3`` allows patch changes; ``~1`` allows minor ones."""
    numbers = _release(version)
    upper = [numbers[0] + 1] if len(numbers) == 1 else [numbers[0], numbers[1] + 1]
    return f">={version},<{_padded(upper, len(numbers))}"


def poetry_constraint(text: str) -> str:
    """A Poetry version constraint as a PEP 440 specifier."""
    if "|" in text:
        raise SourceProblem(f"its version limit {text} can't be read")
    specifiers = []
    joined = re.sub(r"([<>=!~^]+)\s+", r"\1", text.strip())
    for part in re.split(r"[,\s]+", joined):
        if part in ("", "*"):
            continue
        if part.startswith("^"):
            specifiers.append(_caret(part[1:]))
        elif part.startswith("~") and not part.startswith("~="):
            specifiers.append(_tilde(part[1:]))
        else:
            specifiers.append(f"=={part}" if part[0].isdigit() else part)
    return ",".join(specifiers)


def _poetry_requirement(name: str, spec: Any) -> tuple[str, bool]:
    """A dependency as a requirement string, and whether it's optional."""
    if isinstance(spec, str):
        spec = {"version": spec}
    if not isinstance(spec, dict) or any(key in spec for key in POETRY_SOURCES):
        raise SourceProblem(f"its dependency {name} isn't a plain version")
    extras = ",".join(spec.get("extras", []))
    requirement = f"{name}[{extras}]" if extras else name
    requirement += poetry_constraint(str(spec.get("version", "*")))
    markers = [spec["markers"]] if spec.get("markers") else []
    if spec.get("python"):
        for limit in poetry_constraint(str(spec["python"])).split(","):
            operator, version = re.match(r"([<>=!~]+)(.*)", limit).groups()  # type: ignore[union-attr]
            markers.append(f'python_version {operator} "{version}"')
    if markers:
        requirement += "; " + " and ".join(markers)
    return requirement, bool(spec.get("optional"))


def _from_poetry(poetry: dict[str, Any]) -> dict[str, Any]:
    required, optional = [], {}
    python = ""
    for name, spec in poetry.get("dependencies", {}).items():
        if name.lower() == "python":
            python = poetry_constraint(str(spec))
            continue
        requirement, is_optional = _poetry_requirement(name, spec)
        if is_optional:
            optional[name.lower()] = requirement
        else:
            required.append(requirement)
    return {
        "name": poetry["name"],
        "version": poetry.get("version"),
        "description": poetry.get("description", ""),
        "requires-python": python,
        "dependencies": required,
        "optional-dependencies": {
            extra: [optional[n.lower()] for n in names if n.lower() in optional]
            for extra, names in poetry.get("extras", {}).items()
        },
        "scripts": {
            k: v for k, v in poetry.get("scripts", {}).items() if isinstance(v, str)
        },
        "entry-points": poetry.get("plugins", {}),
    }


# -- setup.cfg ------------------------------------------------------------


def _setup_cfg(root: Path) -> configparser.ConfigParser | None:
    path = root / "setup.cfg"
    if not path.is_file():
        return None
    config = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        config.read_string(path.read_text(encoding="utf-8"))
    except (configparser.Error, UnicodeDecodeError) as error:
        raise SourceProblem(f"its setup.cfg can't be read: {error}") from None
    return config


def _lines(value: str) -> list[str]:
    lines = [line.strip() for line in value.splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def _from_setup_cfg(config: configparser.ConfigParser) -> dict[str, Any]:
    options = config["options"] if config.has_section("options") else {}
    if "cmdclass" in options:
        raise SourceProblem("it runs its own build commands")
    if options.get("install_requires", "").strip().startswith("file:"):
        raise SourceProblem("its setup.cfg keeps its requirements in another file")
    version = config.get("metadata", "version", fallback="")
    extras = "options.extras_require"
    entries = "options.entry_points"
    entry_points: dict[str, dict[str, str]] = {}
    if config.has_section(entries):
        for group, text in config[entries].items():
            pairs = (line.partition("=") for line in _lines(text))
            entry_points[group] = {k.strip(): v.strip() for k, _, v in pairs}
    return {
        "name": config.get("metadata", "name"),
        "version": None if version.startswith(("attr:", "file:")) else version or None,
        "description": config.get("metadata", "description", fallback=""),
        "requires-python": options.get("python_requires", ""),
        "dependencies": _lines(options.get("install_requires", "")),
        "optional-dependencies": (
            {k: _lines(v) for k, v in config[extras].items()}
            if config.has_section(extras)
            else {}
        ),
        "entry-points": entry_points,
    }


# -- Where the packages are -----------------------------------------------


def _inside(root: Path, relative: str) -> Path | None:
    path = (root / relative).resolve()
    return path if path.exists() and path.is_relative_to(root.resolve()) else None


def _named_packages(root: Path, data: dict[str, Any]) -> list[str]:
    """The package paths a project lists, relative to `root`."""
    tool = data.get("tool", {})
    wheel = tool.get("hatch", {}).get("build", {}).get("targets", {}).get("wheel", {})
    if wheel.get("packages"):
        return [str(p) for p in wheel["packages"]]
    poetry = tool.get("poetry", {}).get("packages", [])
    if poetry:
        return [f"{p.get('from', '.')}/{p['include']}" for p in poetry]
    setuptools = tool.get("setuptools", {})
    listed = setuptools.get("packages")
    if isinstance(listed, list):
        base = setuptools.get("package-dir", {}).get("", ".")
        return [f"{base}/{p}" for p in listed if "." not in p]
    module = tool.get("flit", {}).get("module", {}).get("name")
    if module:
        return [str(module), f"src/{module}"]
    config = _setup_cfg(root)
    if config is not None and config.has_section("options"):
        names = _lines(config.get("options", "packages", fallback=""))
        if names and not names[0].startswith("find"):
            pairs = _lines(config.get("options", "package_dir", fallback=""))
            base = pairs[0].partition("=")[2].strip() if pairs else "."
            return [f"{base or '.'}/{p}" for p in names if "." not in p]
    return []


def declared_packages(root: Path, data: dict[str, Any]) -> list[Path]:
    """The package folders a project names itself, if it does and they exist.

    A named path must stay inside the project, so an archive can't aim the copy
    at something else.
    """
    found = (_inside(root, name) for name in _named_packages(root, data))
    return sorted({path for path in found if path is not None})


# -- The version ----------------------------------------------------------


def _version_in(path: Path | None) -> str:
    if path is None or not path.is_file():
        return ""
    found = VERSION_LINE.search(path.read_text(encoding="utf-8", errors="replace"))
    return found.group(1) if found else ""


def _version_at_attr(root: Path, attr: str) -> str:
    """The version named by ``pkg.module.__version__``, read as text."""
    parts = attr.strip().split(".")[:-1]
    for base in (".", "src"):
        stem = "/".join([base, *parts])
        for suffix in (".py", "/__init__.py"):
            if text := _version_in(_inside(root, stem + suffix)):
                return text
    return ""


def _text_of(root: Path, relative: str) -> str:
    path = _inside(root, relative.strip())
    return path.read_text(encoding="utf-8").strip() if path and path.is_file() else ""


def named_version(root: Path, data: dict[str, Any], name: str) -> str:
    """The version from the file a project says holds it, or ``""``."""
    tool = data.get("tool", {})
    hatch = tool.get("hatch", {}).get("version", {})
    if hatch.get("path"):
        return _version_in(_inside(root, str(hatch["path"])))
    pdm = tool.get("pdm", {}).get("version", {})
    if pdm.get("source") == "file" and pdm.get("path"):
        return _version_in(_inside(root, str(pdm["path"])))
    dynamic = tool.get("setuptools", {}).get("dynamic", {}).get("version", {})
    if dynamic.get("attr"):
        return _version_at_attr(root, str(dynamic["attr"]))
    if dynamic.get("file"):
        file = dynamic["file"]
        return _text_of(root, file[0] if isinstance(file, list) else file)
    config = _setup_cfg(root)
    if config is not None:
        declared = config.get("metadata", "version", fallback="")
        if declared.startswith("attr:"):
            return _version_at_attr(root, declared.removeprefix("attr:"))
        if declared.startswith("file:"):
            return _text_of(root, declared.removeprefix("file:"))
    backend = str(data.get("build-system", {}).get("build-backend", ""))
    if backend.startswith("flit"):
        module = tool.get("flit", {}).get("module", {}).get("name") or name
        return _version_at_attr(root, f"{module.replace('-', '_')}.__version__")
    return ""


def version_file(root: Path, data: dict[str, Any]) -> str:
    """The file setuptools_scm would write the version to, if it's missing here."""
    scm = data.get("tool", {}).get("setuptools_scm", {})
    file = scm.get("version_file") or scm.get("write_to") or ""
    return str(file) if file and not (root / str(file)).exists() else ""
