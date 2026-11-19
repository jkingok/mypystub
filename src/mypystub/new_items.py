"""Start a new script or project from the bundled templates (#146).

- **Script:** ``templates/script.py``, a one-file prototype with a PEP 723 block
  and a ``main()``.
- **Project:** ``templates/project/``, a Briefcase project that also builds on a
  computer, for iOS, Android or desktop, as it is. Its ``app.py`` has a
  ``main()`` of the same shape as a script's, so a script grows into it.

The templates are ordinary files: placeholders are the module name
``app_template``, the title ``App Template`` (and ``Script Template``), the
distribution name ``app-template``, and, from the details screen, the
description (``App Template description``), the bundle (``com.example``) and
the author (``Jane Developer``), replaced in file contents and paths. That
keeps the templates themselves valid Python that the project's checks cover.

Some of the project's files are **symbolic links** in the repository, to the
launcher's own copies, so there is one of each to maintain: Android's Back
(``android_back.py`` and ``PyBackCallback.java``), the documents provider
(``AppDocumentsProvider.java``) and ``generate_icons.py``. Briefcase copies
what links point to into the app, and New copies the template the same way, so
a new project has real files of its own. Their Java package and class name,
``au.id.jking.mypystub``, become the project's (``<module>.android``). A clone
without symbolic links (Windows, unless ``core.symlinks`` is on) checks each
one out as a one-line file holding its target's path, which would break the
template; :func:`template_problems` finds those, and New refuses to use a
damaged template.

Dependencies aren't asked for: the templates carry TODO comments saying where
they go, since MyPyStub has no editor for them.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from . import template_links
from .paste_import import unique_path

TEMPLATES = Path(__file__).resolve().parent / "resources" / "templates"
SCRIPT_TEMPLATE = TEMPLATES / "script.py"
PROJECT_TEMPLATE = TEMPLATES / "project"
TEXT_SUFFIXES = (".py", ".toml", ".md", ".txt", ".cfg", ".java")
BUNDLE = re.compile(r"[A-Za-z][A-Za-z0-9]*(\.[A-Za-z][A-Za-z0-9]*)+")


class NameProblem(ValueError):
    """A name that can't be used; the message says why."""


class TemplateProblem(Exception):
    """The project template is damaged; the message says how."""


SHARED_PACKAGE = "au.id.jking.mypystub"  # in the files the template links to


def template_problems(root: Path | None = None) -> list[str]:
    """The template's broken links (see :mod:`template_links`), by file."""
    return template_links.problems(PROJECT_TEMPLATE if root is None else root)


def module_name(typed: str) -> str:
    """A Python identifier from what was typed: ``My App 2`` → ``my_app_2``."""
    words = re.findall(r"[A-Za-z0-9]+", typed)
    name = "_".join(words).lower()
    if not name:
        raise NameProblem("Enter a name with at least one letter or digit.")
    return f"app_{name}" if name[0].isdigit() else name


def title_of(typed: str) -> str:
    """The human title: what was typed, tidied to one line."""
    return " ".join(typed.split())


def one_line(typed: str) -> str:
    """What was typed, on one line, without quotes that would end a string."""
    return " ".join(typed.replace('"', "'").replace("\\", "/").split())


def bundle_of(typed: str) -> str:
    """A reverse-domain bundle such as ``com.example``; blank means that one."""
    bundle = typed.strip() or "com.example"
    if not BUNDLE.fullmatch(bundle):
        raise NameProblem(
            "The bundle is a reversed domain name, such as com.example or "
            "au.id.yourname: words of letters and digits, joined by dots."
        )
    return bundle


def _replace_all(text: str, pairs: list[tuple[str, str]]) -> str:
    for old, new in pairs:
        text = text.replace(old, new)
    return text


def create_script(folder: Path, typed: str, description: str = "") -> Path:
    """A new script in `folder`, named from `typed`; never replaces one."""
    name = module_name(typed)
    title = title_of(typed)
    target = unique_path(folder, f"{name}.py")
    about = one_line(description) or "One line about what it does (shown in the list)."
    text = _replace_all(
        SCRIPT_TEMPLATE.read_text(encoding="utf-8"),
        [
            ("Script Template description", f"{title}: {about}"),
            ("Script Template", title),
        ],
    )
    target.write_text(text, encoding="utf-8")
    return target


def create_project(
    folder: Path,
    typed: str,
    description: str = "",
    bundle: str = "",
    author: str = "",
) -> Path:
    """A new project folder in `folder`, named from `typed`; never replaces one."""
    name = module_name(typed)
    title = title_of(typed)
    bundle = bundle_of(bundle)
    target = unique_path(folder, name)
    module = target.name  # app_2 if app was taken: the package follows the folder
    if problems := template_problems():
        raise TemplateProblem(
            "The project template in this build is damaged, so no project was "
            "made. These files should be copies of others but aren't: "
            + "; ".join(problems)
            + ". The app was built from a checkout without symbolic links "
            "(on Windows, turn on core.symlinks and check out again)."
        )
    pairs = [
        ("App Template description", one_line(description) or f"{title}, a Toga app"),
        ("Jane Developer", one_line(author) or "Jane Developer"),
        ("com.example", bundle),
        (SHARED_PACKAGE, f"{module}.android"),
        ("app_template", module),
        ("app-template", module.replace("_", "-")),
        ("App Template", title),
    ]
    # Links are followed: the project gets real copies of the files they share
    shutil.copytree(
        PROJECT_TEMPLATE,
        target,
        symlinks=False,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    # Paths first, deepest first, so renaming a folder can't strand its files
    for path in sorted(target.rglob("*"), key=lambda p: len(p.parts), reverse=True):
        if "app_template" in path.name:
            path.rename(path.with_name(path.name.replace("app_template", module)))
    for path in target.rglob("*"):
        if path.is_file() and path.suffix in TEXT_SUFFIXES:
            text = path.read_text(encoding="utf-8")
            path.write_text(_replace_all(text, pairs), encoding="utf-8")
    return target
