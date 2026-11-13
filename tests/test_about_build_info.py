"""The branch and commit on the About page, for builds not from main."""

import subprocess
from pathlib import Path

import pytest

from mypystub import about, build_info


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    git(tmp_path, "init", "-q", "-b", "main")
    git(
        tmp_path,
        "-c",
        "user.email=a@b",
        "-c",
        "user.name=x",
        "commit",
        "-q",
        "--allow-empty",
        "-m",
        "x",
    )
    git(tmp_path, "tag", "2026.11.12.1")
    return tmp_path


def test_git_says_branch_and_describe(repo: Path) -> None:
    assert build_info.from_git(repo) == build_info.BuildInfo("main", "2026.11.12.1")
    git(repo, "checkout", "-q", "-b", "feature/x")
    (repo / "f").write_text("x")
    git(repo, "add", "f")
    git(repo, "-c", "user.email=a@b", "-c", "user.name=x", "commit", "-q", "-m", "y")
    info = build_info.from_git(repo)
    assert info is not None and info.branch == "feature/x"
    assert info.describe.startswith("2026.11.12.1-1-g")


def test_no_repository_no_info(tmp_path: Path) -> None:
    assert build_info.from_git(tmp_path) is None


def test_not_asked_on_a_device(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(build_info.sys, "platform", "ios")
    assert build_info.from_git(repo) is None


def test_the_file_round_trips_and_bad_files_are_ignored(tmp_path: Path) -> None:
    path = tmp_path / "build_info.json"
    info = build_info.BuildInfo("feature/y", "2026.11.12.1-3-gabc1234-dirty")
    build_info.write(info, path)
    assert build_info.load(path) == info
    path.write_text("not json")
    assert build_info.load(path) is None
    assert build_info.load(tmp_path / "missing.json") is None


def test_rows_only_off_main() -> None:
    assert build_info.rows(None) == []
    assert build_info.rows(build_info.BuildInfo("main", "2026.11.12.1")) == []
    assert build_info.rows(build_info.BuildInfo("feature/y", "abc-dirty")) == [
        ("Branch", "feature/y"),
        ("Commit", "abc-dirty"),
    ]
    assert build_info.rows(build_info.BuildInfo("HEAD", "abc"))[0] == (
        "Branch",
        "(detached)",
    )


def test_about_shows_them_after_the_version(tmp_path: Path) -> None:
    sections = about.collect_environment(
        "MyPyStub",
        "2026.11.12.1",
        {},
        tmp_path / "site",
        packages=False,
        build=build_info.BuildInfo("feature/y", "2026.11.12.1-2-gabc"),
    )
    app = dict(sections)["App"]
    assert [key for key, _ in app][:4] == ["Name", "Version", "Branch", "Commit"]
