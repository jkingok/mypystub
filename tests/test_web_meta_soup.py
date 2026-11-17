"""Messy real-world HTML still gives its metadata (#258)."""

from mypystub import web_meta


def test_unclosed_tags_and_odd_case() -> None:
    page = web_meta.parse_page(
        "<HTML><HEAD><TITLE>  Messy\n Page </TITLE>"
        '<META NAME="Description" CONTENT="Odd case">'
        '<Link REL="Icon" HREF="i.png" SIZES="48X48">'
        "<p>unclosed <b>tags"
    )
    assert page.title == "Messy Page"
    assert page.description == "Odd case"
    assert page.icons == [("i.png", 48)]


def test_rel_with_several_words_and_first_title_wins() -> None:
    page = web_meta.parse_page(
        "<title>First</title><title>Second</title>"
        '<link rel="shortcut  icon" href="f.ico">'
        '<link rel="manifest" href="a.json"><link rel="manifest" href="b.json">'
    )
    assert page.title == "First"
    assert page.icons == [("f.ico", 0)]
    assert page.manifest == "a.json"


def test_empty_content_is_skipped_for_the_next_name() -> None:
    page = web_meta.parse_page(
        '<meta name="description" content="  "><meta property="og:description" content="OG">'
    )
    assert page.description == "OG"
