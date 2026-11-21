"""Work out what kind of text was pasted, so it is saved with the right name (#333).

Pasted text used to be saved as Python whatever it was, so a copied web page
became a ``.py`` that can't run. Now:

1. **magic** names it where it can: ``magic.from_buffer(..., mime=True)``, the
   one call used from python-magic's API, so it works with python-magic
   (libmagic) and with python-magic-pure (the pure-Python replacement the app
   bundles, as a phone has no libmagic). It names a web page, JSON, XML and a
   Python script with a ``#!`` line. The file extension comes from the MIME
   type, with :mod:`mimetypes` for those not listed here.
2. A few **plain checks** cover what a signature can't: a Python script
   without a ``#!`` line, a notebook (JSON), TOML, and Markdown.
3. Otherwise it is **None**: unsure, and the user is asked.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import ast
import json
import mimetypes
import re
import tomllib
from dataclasses import dataclass
from typing import Any

# What magic is shown: enough to recognise a file, not all of a long paste
SAMPLE_BYTES = 4096


@dataclass(frozen=True)
class TextKind:
    """A kind of text: what to call it, and the extension to save it with."""

    name: str
    label: str
    extension: str


PYTHON = TextKind("python", "a Python script", ".py")
HTML = TextKind("html", "a web page", ".html")
MARKDOWN = TextKind("markdown", "Markdown", ".md")
JSON = TextKind("json", "JSON", ".json")
NOTEBOOK = TextKind("notebook", "a Jupyter notebook", ".ipynb")
TOML = TextKind("toml", "TOML", ".toml")
XML = TextKind("xml", "XML", ".xml")
SVG = TextKind("svg", "an SVG image", ".svg")
PLAIN = TextKind("text", "plain text", ".txt")

# The extensions Paste accepts when it has to ask (and `.txt`, if none is given)
CHOICES = (PYTHON, HTML, MARKDOWN, JSON, NOTEBOOK, TOML, XML, SVG, PLAIN)
EXTENSIONS = tuple(kind.extension for kind in CHOICES)

BY_MIME = {
    "text/x-python": PYTHON,
    "text/x-script.python": PYTHON,
    "application/x-python-code": PYTHON,
    "text/html": HTML,
    "application/xhtml+xml": HTML,
    "text/markdown": MARKDOWN,
    "application/json": JSON,
    "application/toml": TOML,
    "text/x-toml": TOML,
    "application/xml": XML,
    "text/xml": XML,
    "image/svg+xml": SVG,
}
# magic's answers that name nothing: plain text it can't say more about, or no
# answer at all
UNHELPFUL = {"text/plain", "application/octet-stream", "inode/x-empty", "data", ""}


def kind_for_extension(name: str) -> TextKind | None:
    """The kind a file name's ending names, if it is one of the CHOICES."""
    lowered = name.lower()
    return next((k for k in CHOICES if lowered.endswith(k.extension)), None)


# -- 1. magic ---------------------------------------------------------------


def magic_mime(text: str) -> str | None:
    """What magic says the MIME type of `text` is, or None if it can't tell.

    Only ``from_buffer(data, mime=True)`` is used. python-magic-pure raises
    for what it doesn't know where libmagic answers ``text/plain``, so any
    failure, and any unhelpful answer, is None. None too when magic isn't
    installed (a development run).
    """
    try:
        import magic
    except ImportError:
        return None
    try:
        answer = str(magic.from_buffer(text.encode()[:SAMPLE_BYTES], mime=True))
    except Exception:  # noqa: BLE001  (PureError, or whatever the backend raises)
        return None
    answer = answer.split(";")[0].strip().lower()
    return None if answer in UNHELPFUL else answer


def kind_for_mime(mime: str) -> TextKind | None:
    """The kind for a MIME type: a known one, or any text type with an extension."""
    if mime in BY_MIME:
        return BY_MIME[mime]
    if not (mime.startswith("text/") or mime.endswith(("+xml", "+json"))):
        return None  # a picture, an archive, ...: not something pasted as text
    extension = mimetypes.guess_extension(mime)
    if not extension:
        return None
    return TextKind(extension.lstrip("."), mime, extension)


# -- 2. plain checks --------------------------------------------------------

SHEBANG = re.compile(r"\A\s*#!.*python")
SCRIPT_BLOCK = re.compile(r"^# /// script\s*$", re.MULTILINE)
TOML_TABLE = re.compile(r"^\s*\[\[?[A-Za-z0-9_.\"' -]+\]\]?\s*(#.*)?$", re.MULTILINE)
HEADING = re.compile(r"^#{1,6}[ \t]+\S", re.MULTILINE)
FENCE = re.compile(r"^\s*(```|~~~)", re.MULTILINE)
LIST_ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])[ \t]+\S", re.MULTILINE)
LINK = re.compile(r"\[[^\]\n]+\]\([^)\s]+\)")
# A statement that is code, not an expression that happens to parse (a word, a
# number, "- a" in a list): such lines are valid Python too
PLAIN_EXPRESSIONS = (
    ast.Name,
    ast.Constant,
    ast.UnaryOp,
    ast.BinOp,
    ast.List,
    ast.Tuple,
    ast.Dict,
    ast.Set,
    ast.Attribute,
    ast.Subscript,
    ast.Compare,
    ast.JoinedStr,
)


def looks_like_python(text: str) -> bool:
    """A script: a ``#!`` or PEP 723 header, or code that parses."""
    if SHEBANG.match(text) or SCRIPT_BLOCK.search(text):
        return True
    try:
        tree = ast.parse(text)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return False
    return any(
        not (isinstance(node, ast.Expr) and isinstance(node.value, PLAIN_EXPRESSIONS))
        for node in tree.body
    )


def looks_like_toml(text: str) -> bool:
    """Parses as TOML and has a ``[table]``: ``x = 1`` alone is Python too."""
    if not TOML_TABLE.search(text):
        return False
    try:
        tomllib.loads(text)
    except tomllib.TOMLDecodeError:
        return False
    return True


def looks_like_markdown(text: str) -> bool:
    """A heading, a fenced block, a link, or a list of two or more."""
    return bool(
        HEADING.search(text)
        or FENCE.search(text)
        or LINK.search(text)
        or len(LIST_ITEM.findall(text)) >= 2
    )


def parsed_json(text: str) -> Any:
    """`text` as JSON if it is an object or array, else None."""
    stripped = text.strip()
    if not stripped.startswith(("{", "[")):
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


def is_notebook(text: str) -> bool:
    """JSON with ``cells`` and ``nbformat``, which is how a notebook begins."""
    data = parsed_json(text)
    return isinstance(data, dict) and "cells" in data and "nbformat" in data


def looks_like_html(text: str) -> bool:
    """Starts like a web page: a doctype or ``<html``."""
    return bool(
        re.match(
            r"\A\s*(?:<!--.*?-->\s*)*<(?:!doctype html|html)",
            text,
            re.IGNORECASE | re.DOTALL,
        )
    )


def sniff(text: str) -> TextKind | None:
    """What the plain checks make of `text`, or None."""
    if is_notebook(text):
        return NOTEBOOK
    if parsed_json(text) is not None:
        return JSON
    if looks_like_html(text):
        return HTML
    if looks_like_toml(text):
        return TOML
    if looks_like_python(text):
        return PYTHON
    if looks_like_markdown(text):
        return MARKDOWN
    return None


def detect(text: str) -> TextKind | None:
    """The kind of `text`, or None if it can't be told (so ask).

    magic first; where it names JSON, a notebook is told from other JSON. When
    it names nothing, or only plain text, the plain checks decide.
    """
    if not text.strip():
        return None
    mime = magic_mime(text)
    kind = kind_for_mime(mime) if mime else None
    if kind is JSON and is_notebook(text):
        return NOTEBOOK
    if kind is not None:
        return kind
    return sniff(text)
