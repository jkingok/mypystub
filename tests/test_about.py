"""Tests for the environment details shown on the About page."""

import platform
import zipfile
from pathlib import Path

import pytest

from mypystub import about


def install_fake_dist(site: Path, name: str, version: str) -> None:
    """Create a minimal .dist-info so importlib.metadata can find `name`."""
    dist_info = site / f"{name}-{version}.dist-info"
    dist_info.mkdir(parents=True)
    (dist_info / "METADATA").write_text(
        f"Metadata-Version: 2.1\nName: {name}\nVersion: {version}\n"
    )


def section(sections: list[about.Section], prefix: str) -> list[about.Row]:
    """Return the rows of the section whose title starts with `prefix`."""
    return next(rows for title, rows in sections if title.startswith(prefix))


def test_python_rows_report_running_interpreter() -> None:
    """The Python section reflects the interpreter running the tests."""
    rows = dict(about.python_rows())
    assert rows["Version"] == platform.python_version()
    assert rows["Implementation"] == platform.python_implementation()


def test_package_sections_split_user_and_bundled(tmp_path: Path) -> None:
    """User-installed packages are listed separately from bundled ones."""
    site = tmp_path / "site_packages"
    install_fake_dist(site, "zz-user-only", "1.0")
    sections = about.package_sections(site)

    titles = [title for title, _ in sections]
    assert titles[0].startswith("Bundled packages (")
    assert titles[1] == "User packages (1)"
    assert section(sections, "User") == [("zz-user-only", "1.0")]
    bundled = dict(section(sections, "Bundled"))
    assert "resolvelib" in bundled
    assert "zz-user-only" not in bundled


def test_package_in_both_places_counts_as_user(tmp_path: Path, monkeypatch) -> None:
    """Once the user site is on sys.path, its packages are not double counted."""
    site = tmp_path / "site_packages"
    install_fake_dist(site, "zz-shadowed", "2.0")
    monkeypatch.syspath_prepend(str(site))
    sections = about.package_sections(site)
    assert "zz-shadowed" not in dict(section(sections, "Bundled"))
    assert dict(section(sections, "User")) == {"zz-shadowed": "2.0"}


def test_missing_user_site_is_empty(tmp_path: Path) -> None:
    """Before anything is installed, the user section is empty."""
    sections = about.package_sections(tmp_path / "nope")
    assert section(sections, "User") == []


def test_collect_environment_sections(tmp_path: Path) -> None:
    """All sections appear in order with the app details first."""
    sections = about.collect_environment(
        "MyPyStub", None, {"Cache": tmp_path}, tmp_path / "site"
    )
    assert [title.split(" (")[0] for title, _ in sections] == [
        "App",
        "Python",
        "Paths",
        "Bundled packages",
        "User packages",
        "Package aliases",
    ]
    assert section(sections, "App") == [("Name", "MyPyStub"), ("Version", "unknown")]
    assert section(sections, "Paths") == [("Cache", str(tmp_path))]


def test_to_text_and_html() -> None:
    """Both renderings include every row, with HTML escaped."""
    sections: list[about.Section] = [
        ("App", [("Name", "<b>stub</b>")]),
        ("User packages (0)", []),
    ]
    text = about.to_text(sections)
    assert "## App\nName: <b>stub</b>\n" in text
    assert "## User packages (0)\n(none)\n" in text

    html = about.to_html(sections)
    assert "<th>Name</th><td>&lt;b&gt;stub&lt;/b&gt;</td>" in html
    assert "<h2>User packages (0)</h2>\n<p>(none)</p>" in html


def test_wheel_installed_package_is_reported(tmp_path: Path) -> None:
    """A real unpacked wheel shows up the same way as on device."""
    from mypystub import piplike

    wheel = tmp_path / "demo-1.0-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zf:
        zf.writestr("demo.py", "")
        zf.writestr(
            "demo-1.0.dist-info/METADATA",
            "Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
        )
        zf.writestr(
            "demo-1.0.dist-info/WHEEL",
            "Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n",
        )
        zf.writestr("demo-1.0.dist-info/RECORD", "")
    site = tmp_path / "site_packages"
    site.mkdir()
    piplike.unpack_wheel(wheel, site)
    assert section(about.package_sections(site), "User") == [("demo", "1.0")]


def test_aliases_section_describes_each_alias(tmp_path: Path) -> None:
    """The About page lists package aliases in effect (#79)."""
    from mypystub.piplike import Alias

    sections = about.collect_environment(
        "MyPyStub",
        None,
        {},
        tmp_path / "site",
        aliases={
            "toga": Alias("bundled", "toga-core"),
            "pyyaml": Alias("substitute", "pyyaml-pure"),
            "fast": Alias("substitute", "fast-pure", when="always"),
        },
    )
    assert section(sections, "Package aliases") == [
        ("fast", "fast-pure (always)"),
        ("pyyaml", "pyyaml-pure (when no compatible wheel)"),
        ("toga", "toga-core (bundled with the app)"),
    ]


REPO = "https://github.com/jkingok/mypystub"


@pytest.mark.parametrize(
    ("home", "version", "url"),
    [
        (REPO, "2026.11.2.3", f"{REPO}/tree/2026.11.2.3"),
        (REPO + "/", "2026.11.2.3", f"{REPO}/tree/2026.11.2.3"),
        (REPO, "0.0.2", REPO),  # a dev run: no release tag, so the repository
        (REPO, None, REPO),
        (None, "2026.11.2.3", None),
        ("javascript:alert(1)", "2026.11.2.3", None),
    ],
)
def test_source_url_points_at_the_release_tag(
    home: str | None, version: str | None, url: str | None
) -> None:
    """Release builds link to their tag; other runs to the repository."""
    assert about.source_url(home, version) == url


def test_source_row_appears_with_a_home_page(tmp_path: Path) -> None:
    """The App section links to the source when the app has a home page."""
    sections = about.collect_environment(
        "MyPyStub",
        "2026.11.2.3",
        {},
        tmp_path / "site",
        home_page=REPO,
    )
    assert ("Source", f"{REPO}/tree/2026.11.2.3") in section(sections, "App")
    without = about.collect_environment("MyPyStub", "1", {}, tmp_path / "site")
    assert [key for key, _ in section(without, "App")] == ["Name", "Version"]


def test_html_links_web_addresses_only() -> None:
    """https values become links; anything else stays text."""
    html = about.to_html(
        [("App", [("Source", f"{REPO}/tree/1.2.3.4"), ("Path", "/var/x")])]
    )
    assert f'<td><a href="{REPO}/tree/1.2.3.4">{REPO}/tree/1.2.3.4</a></td>' in html
    assert "<td>/var/x</td>" in html
