"""The Info view: an HTML report of a script's or project's metadata (#99).

Everything shown comes from the user's files or a download, so it is treated
as untrusted: text is escaped, READMEs and changelogs go through
:func:`mypystub.pages.readme_html`, and only safe links are kept. Only the
metadata that exists is shown, and local absolute paths never are.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import ast
import html
import tomllib
import zipfile
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

from mypystub.pages import readme_html, safe_url
from mypystub.scan import (
    EntryPoint,
    iter_script_metadata,
    project_entry_points,
    read_zipapp_metadata,
)

# Source longer than this shows its first lines, with the rest folded away
SOURCE_PREVIEW_LINES = 300

CHANGELOG_STEMS = ("changelog", "changes", "history", "news")
LICENSE_STEMS = ("license", "licence", "copying")


def escape(text: object) -> str:
    """Escape text for HTML, quotes included."""
    return html.escape(str(text), quote=True)


def section(heading: str, body: str) -> str:
    """A titled section, or nothing if there's nothing to show."""
    return f"<h2>{escape(heading)}</h2>\n{body}\n" if body else ""


def bullet_list(items: Iterable[str]) -> str:
    """Already-escaped items as a list, or nothing if there are none."""
    items = list(items)
    if not items:
        return ""
    return "<ul>\n" + "\n".join(f"<li>{item}</li>" for item in items) + "\n</ul>"


def link(url: str, text: str | None = None) -> str:
    """A link if the URL is safe, otherwise just its text."""
    label = escape(text or url)
    if safe_url(url) and ("://" in url or url.startswith("mailto:")):
        return f'<a href="{escape(url)}">{label}</a>'
    return label


def source_html(source: str, limit: int = SOURCE_PREVIEW_LINES) -> str:
    """Python source, highlighted with line numbers, escaped by Pygments.

    Long files show their first `limit` lines; the rest is in a fold, so the
    page stays quick to lay out until the reader asks for it.
    """
    lines = source.splitlines(keepends=True)
    head, rest = "".join(lines[:limit]), "".join(lines[limit:])
    page = _highlight(head, 1)
    if rest:
        page += (
            f"<details><summary>Show all {len(lines)} lines</summary>\n"
            f"{_highlight(rest, limit + 1)}</details>\n"
        )
    return page


def _highlight(code: str, first_line: int) -> str:
    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import PythonLexer
    except ImportError:
        numbered = "".join(
            f"{n:4d}  {escape(line)}"
            for n, line in enumerate(code.splitlines(keepends=True), first_line)
        )
        return f"<pre><code>{numbered}</code></pre>\n"
    formatter = HtmlFormatter(
        cssclass="codehilite", linenos="inline", linenostart=first_line
    )
    return highlight(code, PythonLexer(), formatter)


def toml_html(text: str) -> str:
    """A TOML block, highlighted if Pygments is there."""
    try:
        from pygments import highlight
        from pygments.formatters import HtmlFormatter
        from pygments.lexers import TOMLLexer
    except ImportError:
        return f"<pre><code>{escape(text)}</code></pre>\n"
    return highlight(text, TOMLLexer(), HtmlFormatter(cssclass="codehilite"))


def entry_html(entry: EntryPoint) -> str:
    """One entry point: name, kind and target."""
    return (
        f"<code>{escape(entry.name)}</code>: {escape(entry.label)} · "
        f"<code>{escape(entry.reference)}</code>"
    )


def dependencies_html(dependencies: Sequence[str]) -> str:
    """A list of requirement strings, or "None"."""
    if not dependencies:
        return "<p>None.</p>"
    return bullet_list(f"<code>{escape(d)}</code>" for d in dependencies)


# -- Scripts -------------------------------------------------------------------


def script_info_html(path: Path, title: str) -> str:
    """The Info page for a single-file script."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"<h1>{escape(title)}</h1>\n<p>Couldn't read the script: {escape(e)}</p>"
    parts = [f"<h1>{escape(title)}</h1>"]
    try:
        docstring = ast.get_docstring(ast.parse(source))
    except SyntaxError as e:
        docstring = None
        parts.append(f"<p>It has a syntax error on line {e.lineno}.</p>")
    if docstring:
        paragraphs = [p.strip() for p in docstring.split("\n\n") if p.strip()]
        parts += [f"<p>{escape(p)}</p>" for p in paragraphs]

    dependencies: list[str] = []
    blocks: list[str] = []
    for kind, text in iter_script_metadata(source):
        blocks.append(text)
        if kind == "script":
            try:
                dependencies += tomllib.loads(text).get("dependencies", [])
            except tomllib.TOMLDecodeError:
                parts.append("<p>Its script metadata block isn't valid TOML.</p>")
    parts.append(section("Dependencies", dependencies_html(dependencies)))
    if blocks:
        parts.append(section("Script metadata", "".join(toml_html(b) for b in blocks)))
    lines = source.count("\n") + (0 if source.endswith("\n") or not source else 1)
    parts.append(
        section(
            "Source",
            f"<p>{escape(path.name)}, {lines} line{'s' if lines != 1 else ''}.</p>\n"
            + source_html(source),
        )
    )
    return "\n".join(p for p in parts if p)


# -- Projects ------------------------------------------------------------------


def find_file(folder: Path, stems: Sequence[str]) -> Path | None:
    """The first file in `folder` whose name, without extension, is in `stems`."""
    try:
        files = sorted(p for p in folder.iterdir() if p.is_file())
    except OSError:
        return None
    for stem in stems:
        for file in files:
            if file.name.lower().split(".", 1)[0] == stem:
                return file
    return None


def within(folder: Path, relative: str) -> Path | None:
    """`relative` inside `folder`, refusing paths that leave it."""
    path = folder / relative
    if not path.resolve().is_relative_to(folder.resolve()):
        return None
    return path if path.is_file() else None


def text_file_html(path: Path) -> str:
    """A README, licence or changelog file, rendered safely."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"<p>Couldn't read {escape(path.name)}: {escape(e)}</p>"
    return readme_html(text, path.name)


def readme_section(folder: Path, readme: Any) -> str:
    """PEP 621 ``readme``: a file name, or a table with ``file`` or ``text``."""
    if isinstance(readme, str):
        path = within(folder, readme)
        return text_file_html(path) if path else ""
    if isinstance(readme, Mapping):
        if "text" in readme:
            markdown = "markdown" in str(readme.get("content-type", ""))
            return readme_html(str(readme["text"]), "README.md" if markdown else "")
        if "file" in readme and (path := within(folder, str(readme["file"]))):
            return text_file_html(path)
    if path := find_file(folder, ("readme",)):
        return text_file_html(path)
    return ""


def license_section(folder: Path, meta: Mapping[str, Any]) -> str:
    """PEP 621/639 ``license`` (an SPDX expression or a table) and its files."""
    parts: list[str] = []
    license_value = meta.get("license")
    files: list[Path] = []
    if isinstance(license_value, str):
        parts.append(f"<p><code>{escape(license_value)}</code></p>")
    elif isinstance(license_value, Mapping):
        if "text" in license_value:
            parts.append(f"<pre>{escape(license_value['text'])}</pre>")
        elif "file" in license_value and (
            path := within(folder, str(license_value["file"]))
        ):
            files.append(path)
    for pattern in meta.get("license-files", []) or []:
        if isinstance(pattern, str) and ".." not in Path(pattern).parts:
            files += sorted(p for p in folder.glob(pattern) if p.is_file())
    if not parts and not files and (path := find_file(folder, LICENSE_STEMS)):
        files.append(path)
    seen: set[Path] = set()
    for path in files:
        if path in seen or not path.resolve().is_relative_to(folder.resolve()):
            continue
        seen.add(path)
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        parts.append(f"<h3>{escape(path.name)}</h3>\n<pre>{escape(text)}</pre>")
    return "\n".join(parts)


def people_html(people: Any) -> list[str]:
    """PEP 621 ``authors``/``maintainers`` as escaped items."""
    items: list[str] = []
    for person in people if isinstance(people, list) else []:
        if not isinstance(person, Mapping):
            continue
        name, email = person.get("name"), person.get("email")
        if name and email:
            items.append(link(f"mailto:{email}", f"{name} <{email}>"))
        elif email:
            items.append(link(f"mailto:{email}", str(email)))
        elif name:
            items.append(escape(name))
    return items


def project_info_html(
    folder: Path,
    title: str,
    *,
    entry: EntryPoint | None = None,
    show_entries: bool = True,
) -> str:
    """The Info page for a project, a package of entry points, or one entry.

    `entry` names the entry point being described, if any; `show_entries`
    lists all of the project's entry points.
    """
    try:
        with open(folder / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
    except (OSError, tomllib.TOMLDecodeError) as e:
        return f"<h1>{escape(title)}</h1>\n<p>Couldn't read pyproject.toml: {escape(e)}</p>"
    meta: Mapping[str, Any] = data.get("project", {})
    tool = data.get("tool", {}).get("stub_launcher", {})
    parts = [f"<h1>{escape(title)}</h1>"]
    if description := meta.get("description"):
        parts.append(f"<p>{escape(description)}</p>")
    if entry is not None:
        parts.append(
            f"<p>An entry point of {escape(meta.get('name', folder.name))}: "
            f"{entry_html(entry)}</p>"
        )

    details: list[str] = []
    if name := meta.get("name"):
        details.append(f"Name: <code>{escape(name)}</code>")
    if version := meta.get("version"):
        details.append(f"Version: {escape(version)}")
    if requires := meta.get("requires-python"):
        details.append(f"Requires Python: <code>{escape(requires)}</code>")
    if authors := people_html(meta.get("authors")):
        details.append("Authors: " + ", ".join(authors))
    if maintainers := people_html(meta.get("maintainers")):
        details.append("Maintainers: " + ", ".join(maintainers))
    if run := tool.get("entry_point"):
        details.append(f"Runs: <code>{escape(run)}</code>")
    parts.append(section("Details", bullet_list(details)))

    parts.append(
        section("Dependencies", dependencies_html(meta.get("dependencies", [])))
    )
    extras = meta.get("optional-dependencies", {})
    if isinstance(extras, Mapping) and extras:
        parts.append(
            section(
                "Optional dependencies",
                bullet_list(
                    f"<code>{escape(group)}</code>: "
                    + ", ".join(f"<code>{escape(d)}</code>" for d in deps)
                    for group, deps in extras.items()
                    if isinstance(deps, list)
                ),
            )
        )
    if show_entries and not tool.get("entry_point"):
        entries = project_entry_points(meta)
        parts.append(section("Entry points", bullet_list(map(entry_html, entries))))
    urls = meta.get("urls", {})
    if isinstance(urls, Mapping):
        parts.append(
            section(
                "Links",
                bullet_list(
                    f"{escape(label)}: {link(str(url))}" for label, url in urls.items()
                ),
            )
        )
    parts.append(section("README", readme_section(folder, meta.get("readme"))))
    parts.append(section("Licence", license_section(folder, meta)))
    if changelog := find_file(folder, CHANGELOG_STEMS):
        parts.append(section("Changelog", text_file_html(changelog)))
    return "\n".join(p for p in parts if p)


# -- Zipapps ---------------------------------------------------------------------


def zipapp_info_html(
    path: Path,
    title: str,
    *,
    entry: EntryPoint | None = None,
    show_entries: bool = True,
) -> str:
    """The Info page for a ``.pyz`` zipapp: its dist-info, and its ``__main__.py``.

    Nothing is extracted. Whatever metadata the archive has is shown, and an
    archive that can't be read says so.
    """
    try:
        with zipfile.ZipFile(path) as archive:
            main = archive.read("__main__.py").decode("utf-8", errors="replace")
    except KeyError:
        main = ""
    except (OSError, zipfile.BadZipFile) as error:
        return (
            f"<h1>{escape(title)}</h1>\n"
            f"<p>Couldn't read {escape(path.name)}: {escape(error)}</p>"
        )
    meta = read_zipapp_metadata(path)
    parts = [f"<h1>{escape(title)}</h1>"]
    if description := meta.get("description"):
        parts.append(f"<p>{escape(description)}</p>")
    if entry is not None:
        parts.append(
            f"<p>An entry point of {escape(meta.get('name', path.stem))}: "
            f"{entry_html(entry)}</p>"
        )
    details = [f"File: <code>{escape(path.name)}</code>"]
    if name := meta.get("name"):
        details.append(f"Name: <code>{escape(name)}</code>")
    if version := meta.get("version"):
        details.append(f"Version: {escape(version)}")
    parts.append(section("Details", bullet_list(details)))
    parts.append(
        section("Dependencies", dependencies_html(meta.get("dependencies", [])))
    )
    if show_entries:
        parts.append(
            section(
                "Entry points",
                bullet_list(map(entry_html, project_entry_points(meta))),
            )
        )
    urls = meta.get("urls", {})
    parts.append(
        section(
            "Links",
            bullet_list(
                f"{escape(label)}: {link(str(url))}" for label, url in urls.items()
            ),
        )
    )
    if readme := meta.get("readme"):
        markdown = "markdown" in str(readme.get("content-type", ""))
        parts.append(
            section(
                "README",
                readme_html(str(readme["text"]), "README.md" if markdown else ""),
            )
        )
    if main.strip():
        lines = main.count("\n") + (0 if main.endswith("\n") else 1)
        parts.append(
            section(
                "Source",
                f"<p>__main__.py, {lines} line{'s' if lines != 1 else ''}.</p>\n"
                + source_html(main),
            )
        )
    return "\n".join(p for p in parts if p)
