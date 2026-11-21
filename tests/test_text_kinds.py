"""Naming pasted text: magic where it can, plain checks where it can't (#333)."""

from __future__ import annotations

import sys
import types

import pytest

from mypystub import text_kinds as k

PAGE = "<!DOCTYPE html>\n<html><head><title>x</title></head><body>hi</body></html>\n"
NOTEBOOK = '{"cells": [], "metadata": {}, "nbformat": 4, "nbformat_minor": 5}'


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("#!/usr/bin/env python3\nprint('hi')\n", k.PYTHON),
        ("import os\nprint(os.getcwd())\n", k.PYTHON),
        ("# /// script\n# dependencies = ['x']\n# ///\nimport os\n", k.PYTHON),
        ("x = 1\ny = x + 2\n", k.PYTHON),
        ("def f():\n    return 1\n", k.PYTHON),
        (PAGE, k.HTML),
        ("<html><body>hi</body></html>", k.HTML),
        ('{"a": 1, "b": [1, 2]}', k.JSON),
        (NOTEBOOK, k.NOTEBOOK),
        ('[project]\nname = "x"\nversion = "1"\n', k.TOML),
        ('<?xml version="1.0"?><a><b/></a>', k.XML),
        ('<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>', k.SVG),
        ("# Title\n\n- one\n- two\n\n```python\nprint(1)\n```\n", k.MARKDOWN),
        ("- one\n- two\n- three\n", k.MARKDOWN),
        ("See [the docs](https://example.com) for more.\n", k.MARKDOWN),
    ],
)
def test_each_kind_is_recognised(text: str, expected: k.TextKind) -> None:
    assert k.detect(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "Just some words about my day.\n",
        "hello",
        "42",
        "<div><p>hello</p></div>\n",  # a fragment has no signature
        "body { color: red; }\n",
        "a,b,c\n1,2,3\n",
        "",
        "   \n",
    ],
)
def test_what_cannot_be_told_is_none_so_the_user_is_asked(text: str) -> None:
    assert k.detect(text) is None


def test_python_that_is_also_toml_is_python() -> None:
    """``x = 1`` is valid TOML too; only a [table] makes it TOML."""
    assert k.detect("x = 1\n") == k.PYTHON
    assert k.detect("[tool]\nx = 1\n") == k.TOML


def test_a_word_a_number_or_a_list_is_not_code() -> None:
    for text in ("hello", "42", "- a\n- b", "[1, 2]"):
        assert not k.looks_like_python(text)


def test_a_notebook_is_told_from_other_json() -> None:
    assert k.is_notebook(NOTEBOOK)
    assert not k.is_notebook('{"cells": []}')
    assert k.detect('{"cells": [], "other": 1}') == k.JSON


# -- the magic part ---------------------------------------------------------


def fake_magic(monkeypatch: pytest.MonkeyPatch, answer: object) -> list[tuple]:
    """A `magic` module with ONLY from_buffer: the limited API, as pure has."""
    calls: list[tuple] = []
    module = types.ModuleType("magic")

    def from_buffer(buffer: bytes, mime: bool = False) -> str:
        calls.append((buffer, mime))
        if isinstance(answer, Exception):
            raise answer
        return str(answer)

    module.from_buffer = from_buffer  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "magic", module)
    return calls


def test_only_from_buffer_with_mime_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = fake_magic(monkeypatch, "text/html")
    assert k.detect("anything") == k.HTML
    assert calls == [(b"anything", True)]


def test_a_long_paste_gives_magic_only_a_sample(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = fake_magic(monkeypatch, "text/html")
    k.detect("x" * 100_000)
    assert len(calls[0][0]) == k.SAMPLE_BYTES


@pytest.mark.parametrize("answer", ["text/plain", "application/octet-stream", "data"])
def test_an_unhelpful_answer_falls_to_the_plain_checks(
    monkeypatch: pytest.MonkeyPatch, answer: str
) -> None:
    fake_magic(monkeypatch, answer)
    assert k.detect("# Title\n\nwords\n") == k.MARKDOWN  # libmagic says plain text


def test_magic_raising_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """python-magic-pure raises PureError for what it doesn't know."""
    fake_magic(monkeypatch, LookupError("Could not identify file"))
    assert k.detect("import os\n") == k.PYTHON  # by the plain checks
    assert k.detect("words and more words") is None


def test_magic_not_installed_is_not_an_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "magic", None)  # makes `import magic` fail
    assert k.magic_mime("anything") is None
    assert k.detect(PAGE) == k.HTML  # the plain checks still know a web page


def test_the_extension_comes_from_the_mime_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_magic(monkeypatch, "text/css")
    css = k.detect("body { color: red; }")
    assert css is not None and css.extension == ".css"
    fake_magic(monkeypatch, "text/csv; charset=us-ascii")  # libmagic adds a charset
    csv = k.detect("a,b\n1,2\n")
    assert csv is not None and csv.extension == ".csv"


def test_a_picture_or_archive_is_not_text(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_magic(monkeypatch, "image/png")
    assert k.detect("not really a picture") is None
    fake_magic(monkeypatch, "application/zip")
    assert k.detect("not really an archive") is None


def test_the_real_pure_backend_names_a_page_and_raises_for_prose() -> None:
    """With python-magic-pure installed (it is a dependency of the app)."""
    magic = pytest.importorskip("magic")
    assert magic.from_buffer(PAGE.encode(), mime=True) == "text/html"
    assert k.magic_mime("Just prose.") is None


def test_kind_for_extension_picks_the_choice_a_name_ends_in() -> None:
    assert k.kind_for_extension("Page.HTML") == k.HTML
    assert k.kind_for_extension("notes.md") == k.MARKDOWN
    assert k.kind_for_extension("tool") is None
