"""Find what the launcher can run: scripts, projects, zipapps and folders.

Reads PEP 723 script metadata, ``pyproject.toml`` (including entry points),
zipapp metadata and folder contents. Resolving and installing dependencies
is :mod:`mypystub.piplike`; this only looks.
"""

import ast
import configparser
import email
import platform
import re
import tomllib
import zipfile
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from .piplike import parse_aliases

PEP723_BLOCK = re.compile(
    r"(?m)^# /// (?P<type>[a-zA-Z0-9-]+)$\s(?P<content>(^#(| .*)$\s)+)^# ///$"
)

# Loose scripts that are part of the launcher itself, not prototypes
RESERVED_SCRIPTS = frozenset({"patch_app.py", "__init__.py"})

# Subtitle for a loose script without a module docstring
DEFAULT_SCRIPT_SUBTITLE = "Standalone Python script."

# Folders that never hold prototypes
SKIPPED_FOLDERS = frozenset({"__pycache__", "site-packages", "site_packages"})


def iter_script_metadata(script: str) -> Iterator[tuple[str, str]]:
    """Yield ``(type, toml_text)`` for each PEP 723 metadata block in a script."""
    for match in PEP723_BLOCK.finditer(script):
        yield (
            match.group("type"),
            "".join(
                line[2:] if line.startswith("# ") else line[1:]
                for line in match.group("content").splitlines(keepends=True)
            ),
        )


def docstring_summary(source: str) -> str | None:
    """Return the first line of a module's docstring, or None if there isn't one.

    Scripts that fail to parse still get listed, so a syntax error returns None
    rather than raising; the error is reported when the script is run.
    """
    try:
        docstring = ast.get_docstring(ast.parse(source))
    except SyntaxError:
        return None
    if not docstring:
        return None
    return docstring.strip().splitlines()[0].strip() or None


def scan_script(item: Path) -> dict[str, Any] | None:
    """Describe a loose ``.py`` prototype, or return None if it cannot run here.

    Dependencies come from the PEP 723 ``script`` block. A script whose
    ``requires-python`` excludes the running interpreter is skipped.

    The same block may hold a ``[tool.stub_launcher]`` table with the keys a
    project folder uses: ``display_name`` (else the file name), ``description``
    (else the first line of the module docstring) and ``icon`` (a path relative
    to the script's folder).
    """
    source = item.read_text(encoding="utf-8")
    dependencies: list[str] = []
    launcher: dict[str, Any] = {}
    for kind, text in iter_script_metadata(source):
        if kind != "script":
            continue
        config = tomllib.loads(text)
        dependencies += config.get("dependencies", [])
        launcher |= config.get("tool", {}).get("stub_launcher", {})
        if requires_python := config.get("requires-python"):
            current = platform.python_version()
            if Version(current) not in SpecifierSet(requires_python):
                print(
                    f"Skipping {item.name} needs Python {requires_python} not {current}"
                )
                return None

    return {
        "title": launcher.get("display_name") or item.stem,
        "subtitle": launcher.get("description")
        or docstring_summary(source)
        or DEFAULT_SCRIPT_SUBTITLE,
        "icon_path": _icon_within(item.parent, launcher.get("icon")),
        "entry_point": item,
        "folder_root": item.parent,
        "dependencies": dependencies,
        "aliases": parse_aliases(launcher.get("aliases", {})),
        "kind": "script",
    }


def _icon_within(folder: Path, relative: str | None) -> Path | None:
    """Resolve an icon path relative to ``folder``, refusing paths outside it."""
    if not relative:
        return None
    icon = folder / relative
    if not icon.resolve().is_relative_to(folder.resolve()):
        print(f"Ignoring icon outside {folder}: {relative}")
        return None
    return icon


@dataclass(frozen=True)
class EntryPoint:
    """One of a project's PEP 621 entry points.

    ``kind`` is ``"cli"`` for ``[project.scripts]``, ``"gui"`` for
    ``[project.gui-scripts]``, and ``"other"`` for any
    ``[project.entry-points.<group>]``, whose group is kept in ``group``.
    """

    name: str
    reference: str
    kind: str
    group: str

    @property
    def label(self) -> str:
        """How the list describes the kind: Console, GUI, or the group's name."""
        return {"cli": "Console", "gui": "GUI"}.get(self.kind, self.group)


def project_entry_points(project_meta: Mapping[str, Any]) -> list[EntryPoint]:
    """Every entry point a ``[project]`` table declares, sorted by name."""
    found: list[EntryPoint] = []
    tables: list[tuple[str, str, Any]] = [
        ("cli", "console_scripts", project_meta.get("scripts", {})),
        ("gui", "gui_scripts", project_meta.get("gui-scripts", {})),
    ]
    other = project_meta.get("entry-points", {})
    if isinstance(other, Mapping):
        tables += [("other", group, table) for group, table in other.items()]
    for kind, group, table in tables:
        if not isinstance(table, Mapping):
            continue
        for name, reference in table.items():
            if isinstance(reference, str):
                found.append(EntryPoint(str(name), reference, kind, str(group)))
    return sorted(found, key=lambda e: (e.name.casefold(), e.name, e.group))


def scan_project(item: Path) -> dict[str, Any]:
    """Describe a project folder from its ``pyproject.toml``.

    ``[tool.stub_launcher] entry_point`` names the file to run. Without it,
    the project's PEP 621 entry points decide: one is run when the project is
    tapped, and several make the project a ``"package"`` that opens like a
    folder, listing them. A project with neither runs ``main.py``.
    """
    with open(item / "pyproject.toml", "rb") as f:
        toml_data = tomllib.load(f)

    # Read standard PEP 621 table
    project_meta = toml_data.get("project", {})
    name = project_meta.get("name", item.name)
    desc = project_meta.get("description", "Project directory module.")

    # Read tool overrides
    tool_meta = toml_data.get("tool", {}).get("stub_launcher", {})
    icon_relative = tool_meta.get("icon")

    row: dict[str, Any] = {
        "title": tool_meta.get("display_name", name),
        "subtitle": desc,
        "icon_path": item / icon_relative if icon_relative else None,
        # Target launch file path relative to its home folder
        "entry_point": item / tool_meta.get("entry_point", "main.py"),
        "folder_root": item / tool_meta.get("import_path", "src"),
        # PEP 621 dependencies list (default to empty list if missing)
        "dependencies": project_meta.get("dependencies", []),
        "aliases": parse_aliases(tool_meta.get("aliases", {})),
        "project_dir": item,
        "kind": "project",
    }
    if "entry_point" in tool_meta:
        return row
    entries = project_entry_points(project_meta)
    if len(entries) == 1:
        row["entry"] = entries[0]  # the project's implied entry point
    elif entries:
        del row["entry_point"]
        row["kind"] = "package"
        row["entries"] = entries
    return row


def entry_rows(package: Mapping[str, Any]) -> list[dict[str, Any]]:
    """The rows listed inside a package with several entry points."""
    shared = ("folder_root", "project_dir", "dependencies", "aliases")
    return [
        {
            "title": entry.name,
            "subtitle": f"{entry.label} · {entry.reference}",
            "icon_path": None,
            "entry": entry,
            "package_title": package["title"],
            "kind": "entry",
            **{key: package[key] for key in shared},
        }
        for entry in package["entries"]
    ]


# What a folder row counts, in the order shown, with a word and a compact symbol
SUMMARY_KINDS = {
    "subfolder": "📁",
    "package": "📦",  # projects and zipapps, which run as one entry
    "script": "🐍",
    "other file": "📄",
}


def read_zipapp_metadata(archive: Path) -> dict[str, Any]:
    """What a zipapp's ``*.dist-info`` says about it, as a PEP 621-like table.

    Read with :mod:`zipfile` only; nothing is extracted. Whatever is missing
    or unreadable is simply left out, so an archive with no metadata gives
    ``{}``. The result has the keys of a ``[project]`` table (``name``,
    ``version``, ``description``, ``dependencies``, ``urls``, ``scripts``,
    ``gui-scripts``, ``entry-points``), plus ``readme`` (text and content type)
    when the metadata has a long description.
    """
    meta: dict[str, Any] = {}
    try:
        with zipfile.ZipFile(archive) as zf:
            names = zf.namelist()
            info = next((n for n in names if n.endswith(".dist-info/METADATA")), None)
            points = next(
                (n for n in names if n.endswith(".dist-info/entry_points.txt")), None
            )
            if info:
                message = email.message_from_bytes(zf.read(info))
                if name := message.get("Name"):
                    meta["name"] = name
                if version := message.get("Version"):
                    meta["version"] = version
                if summary := message.get("Summary"):
                    meta["description"] = summary
                requires = [
                    r
                    for r in message.get_all("Requires-Dist") or []
                    if "extra ==" not in r
                ]
                if requires:
                    meta["dependencies"] = requires
                urls = {}
                for item in message.get_all("Project-URL") or []:
                    label, _, url = item.partition(",")
                    urls[label.strip()] = url.strip()
                if urls:
                    meta["urls"] = urls
                body = message.get_payload(decode=True)
                if isinstance(body, bytes) and body.strip():
                    meta["readme"] = {
                        "text": body.decode("utf-8", errors="replace"),
                        "content-type": message.get("Description-Content-Type", ""),
                    }
            if points:
                parser = configparser.ConfigParser(
                    delimiters=("=",), interpolation=None
                )
                parser.optionxform = str  # type: ignore[assignment,method-assign]
                parser.read_string(zf.read(points).decode("utf-8", errors="replace"))
                groups = {g: dict(parser[g]) for g in parser.sections()}
                if scripts := groups.pop("console_scripts", None):
                    meta["scripts"] = scripts
                if gui := groups.pop("gui_scripts", None):
                    meta["gui-scripts"] = gui
                if groups:
                    meta["entry-points"] = groups
    except (OSError, zipfile.BadZipFile, KeyError, configparser.Error):
        pass  # not scanning for problems: they show up when it runs
    return meta


def scan_zipapp(item: Path) -> dict[str, Any]:
    """Describe a ``.pyz`` zipapp the way :func:`scan_project` describes a project.

    A zipapp with several entry points is a ``"package"``, one with a single
    entry point runs it, and any other runs its ``__main__.py``. It is trusted
    as it is: nothing is validated, so a broken archive is a run-time error.
    """
    meta = read_zipapp_metadata(item)
    row: dict[str, Any] = {
        "title": item.stem,
        "subtitle": meta.get("description") or "Zipapp",
        "icon_path": None,
        "entry_point": item,
        "folder_root": item,
        "dependencies": [],
        "aliases": {},
        "project_dir": item,
        "kind": "zipapp",
    }
    entries = project_entry_points(meta)
    if len(entries) == 1:
        row["entry"] = entries[0]
    elif entries:
        del row["entry_point"]
        row["kind"] = "package"
        row["entries"] = entries
    return row


def folder_counts(folder: Path) -> dict[str, int] | None:
    """Count what the list would show inside `folder`, without parsing files.

    Hidden entries, caches and launcher files aren't counted. A ``.pyz``
    zipapp counts as a package, like a project folder. None if the folder
    can't be read. This lists one directory per folder row, so it is cheap but
    not free.
    """
    counts = dict.fromkeys(SUMMARY_KINDS, 0)
    try:
        children = list(folder.iterdir())
    except OSError:
        return None
    for child in children:
        if child.name.startswith("."):
            continue
        if child.is_dir():
            if (child / "pyproject.toml").exists():
                counts["package"] += 1
            elif child.name not in SKIPPED_FOLDERS:
                counts["subfolder"] += 1
        elif child.suffix == ".py":
            if child.name not in RESERVED_SCRIPTS:
                counts["script"] += 1
        elif child.suffix == ".pyz":
            counts["package"] += 1
        else:
            counts["other file"] += 1
    return counts


def folder_summary(folder: Path) -> str:
    """Summarise a folder in words, such as "2 subfolders, 1 package, 3 scripts".

    "Empty folder" if there is nothing to show, "Folder" if it can't be read.
    """
    counts = folder_counts(folder)
    if counts is None:
        return "Folder"
    parts = [f"{n} {kind}{'' if n == 1 else 's'}" for kind, n in counts.items() if n]
    return ", ".join(parts) if parts else "Empty folder"


def folder_summary_compact(folder: Path) -> str:
    """Summarise a folder in a short line for a narrow row: "📁 2 · 📦 1 · 🐍 3".

    The same counts as :func:`folder_summary`, a symbol each, so the line isn't
    truncated on a phone. Kinds that aren't there are left out.
    """
    counts = folder_counts(folder)
    if counts is None:
        return "Folder"
    parts = [f"{SUMMARY_KINDS[kind]} {n}" for kind, n in counts.items() if n]
    return " · ".join(parts) if parts else "Empty folder"


def scan_folder(item: Path) -> dict[str, Any]:
    """Describe a plain folder that the launcher can navigate into."""
    return {
        "title": item.name,
        "subtitle": folder_summary_compact(item),
        "icon_path": None,
        "folder": item,
        "dependencies": [],
        "kind": "folder",
    }


def scan_all_prototypes(base_dir: Path) -> Iterable[Mapping[str, Any]]:
    """List the prototypes and sub-folders directly inside ``base_dir``.

    Folders come first, then scripts and project folders, each sorted by name.
    Folders with a ``pyproject.toml`` are runnable projects; other folders are
    returned with a ``folder`` key so the launcher can drill into them.
    """
    folders: list[Mapping[str, Any]] = []
    prototypes: list[Mapping[str, Any]] = []
    print(f"Scanning for launcher prototypes in: {base_dir}")

    if not base_dir.is_dir():
        return prototypes

    for item in sorted(base_dir.iterdir(), key=lambda x: x.name.lower()):
        # Skip hidden files/folders (like .DS_Store or system bits)
        if item.name.startswith("."):
            continue

        try:
            # --- CASE A: The "Toy Script" (Loose .py file) ---
            if item.is_file() and item.suffix == ".py":
                # Don't accidentally auto-load your main launcher scripts
                if item.name not in RESERVED_SCRIPTS and (entry := scan_script(item)):
                    prototypes.append(entry)

            # --- CASE A2: A zipapp (.pyz), trusted as it is ---
            elif item.is_file() and item.suffix == ".pyz":
                prototypes.append(scan_zipapp(item))

            # --- CASE B: The "Full Project" (Folder with pyproject.toml) ---
            elif item.is_dir() and (item / "pyproject.toml").exists():
                prototypes.append(scan_project(item))

            # --- CASE C: A plain folder to navigate into ---
            elif item.is_dir() and item.name not in SKIPPED_FOLDERS:
                folders.append(scan_folder(item))
        except (OSError, ValueError) as e:
            # ValueError covers TOMLDecodeError, bad specifiers and bad versions
            print(f"Skipping malformed prototype {item.name}: {e}")

    return folders + prototypes


def relative_folder(base_dir: Path, folder: Path) -> Path:
    """Return ``folder`` relative to ``base_dir``, refusing to leave ``base_dir``.

    Used for launcher navigation so ``..`` and symlinks cannot escape the
    prototype root.
    """
    base = base_dir.resolve()
    target = folder.resolve()
    if not target.is_relative_to(base):
        return Path()
    return target.relative_to(base)
