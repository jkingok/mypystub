"""Web app Info: highlighted, folded page source and assets (#234)."""

from pathlib import Path

import pytest

from mypystub import info_pages


def make(tmp_path: Path, lines: int = 3) -> Path:
    app = tmp_path / "site"
    app.mkdir()
    body = "\n".join(f"<p>line {n} &lt;x&gt;</p>" for n in range(lines))
    (app / "index.html").write_text(
        f"<title>T</title>\n<script>alert(1)</script>\n{body}"
    )
    (app / "style.css").write_text("body { color: red; }")
    (app / "app.js").write_text("const x = 1;")
    (app / "notes.txt").write_text("not shown")
    return app


def test_the_page_source_is_highlighted_and_escaped(tmp_path: Path) -> None:
    pytest.importorskip("pygments")
    page = info_pages.web_info_html(make(tmp_path), "index.html", "site")
    assert 'class="codehilite"' in page
    assert "<script>alert(1)</script>" not in page  # the page's HTML stays text
    assert "&lt;" in page


def test_a_long_page_folds_after_the_limit(tmp_path: Path) -> None:
    page = info_pages.web_info_html(
        make(tmp_path, info_pages.SOURCE_PREVIEW_LINES + 20), "index.html", "site"
    )
    assert "<details><summary>Show all" in page


def test_a_folders_stylesheets_and_scripts_are_shown(tmp_path: Path) -> None:
    page = info_pages.web_info_html(make(tmp_path), "index.html", "site")
    assert "<h2>style.css</h2>" in page and "<h2>app.js</h2>" in page
    assert "notes.txt" not in page


def test_a_single_page_shows_no_neighbours(tmp_path: Path) -> None:
    folder = make(tmp_path)
    (folder / "solo.html").write_text("<p>hi</p>")
    page = info_pages.web_info_html(folder, "solo.html", "solo")
    assert "style.css" not in page


def test_without_pygments_the_source_is_plain_but_escaped(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import builtins

    real = builtins.__import__

    def no_pygments(name: str, *args, **kwargs):
        if name.startswith("pygments"):
            raise ImportError(name)
        return real(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_pygments)
    html = info_pages.source_html("<b>x</b>", language="html")
    assert "&lt;b&gt;" in html and "<b>x</b>" not in html


def test_python_highlighting_is_unchanged() -> None:
    pytest.importorskip("pygments")
    assert 'class="codehilite"' in info_pages.source_html("print(1)\n")
