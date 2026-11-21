"""Update-check answers kept for a day per version, and when the last check was."""

import json
from datetime import date, datetime
from pathlib import Path

import httpx2

from mypystub import git_updates, maintenance
from mypystub.update_cache import UpdateCache

DAY = date(2026, 11, 21)
NEXT = date(2026, 11, 22)


def test_an_answer_lasts_the_day_for_its_version(tmp_path: Path) -> None:
    path = tmp_path / "checks.json"
    cache = UpdateCache(path, DAY)
    cache.put("pypi", "rich", "14.1", version="14.0")
    cache.save(datetime(2026, 11, 21, 10, 32))
    again = UpdateCache(path, DAY)
    assert again.get("pypi", "rich", "14.0") == "14.1"
    assert again.get("pypi", "rich", "14.1") is None  # another version
    assert again.checked == datetime(2026, 11, 21, 10, 32)
    tomorrow = UpdateCache(path, NEXT)
    assert tomorrow.get("pypi", "rich", "14.0") is None  # stale
    assert tomorrow.last("pypi", "rich", "14.0") == "14.1"  # still shown


def test_a_missing_or_damaged_file_starts_again(tmp_path: Path) -> None:
    assert UpdateCache(tmp_path / "none.json", DAY).checked is None
    bad = tmp_path / "bad.json"
    bad.write_text("{not json")
    assert UpdateCache(bad, DAY).entries == {}
    bad.write_text(json.dumps({"entries": [], "checked": 3}))
    assert UpdateCache(bad, DAY).checked is None


def counting_client(answers: dict[str, str]) -> tuple[httpx2.Client, list[str]]:
    asked: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(str(request.url))
        text = answers.get(str(request.url))
        return httpx2.Response(200, text=text) if text else httpx2.Response(404)

    return httpx2.Client(transport=httpx2.MockTransport(handler)), asked


def test_pypi_is_asked_once_a_day_per_version(tmp_path: Path) -> None:
    url = maintenance.PYPI_JSON_URL.format(name="rich")
    client, asked = counting_client({url: json.dumps({"info": {"version": "14.1"}})})
    cache = UpdateCache(tmp_path / "c.json", DAY)
    first = maintenance.find_updates(client, {"rich": "14.0"}, cache=cache)
    second = maintenance.find_updates(client, {"rich": "14.0"}, cache=cache)
    assert first == second and str(first[0].latest) == "14.1"
    assert len(asked) == 1
    maintenance.find_updates(client, {"rich": "14.1"}, cache=cache)  # updated
    assert len(asked) == 2


def test_offline_uses_only_what_was_remembered(tmp_path: Path) -> None:
    cache = UpdateCache(tmp_path / "c.json", NEXT)
    cache.entries = {
        "pypi": {"rich": {"version": "14.0", "day": "2026-11-21", "value": "14.1"}}
    }
    found = maintenance.find_updates(
        None,  # type: ignore[arg-type]
        {"rich": "14.0", "new": "1.0"},
        cache=cache,
        offline=True,
    )
    assert [u.name for u in found] == ["rich"]


def test_python_and_git_answers_are_kept_too(tmp_path: Path) -> None:
    cache = UpdateCache(tmp_path / "c.json", DAY)
    asked: list[str] = []

    def fake_check(client: object, current: str) -> maintenance.PythonStatus:
        asked.append("python.org")
        return maintenance.PythonStatus(
            maintenance.Version(current), maintenance.Version("3.15.2"), None, None
        )

    real = maintenance.check_python
    maintenance.check_python = fake_check  # type: ignore[assignment]
    try:
        for _ in range(2):
            status = maintenance.check_python_cached(None, "3.15.1", cache)  # type: ignore[arg-type]
            assert status is not None and str(status.latest_patch) == "3.15.2"
    finally:
        maintenance.check_python = real  # type: ignore[assignment]
    assert asked == ["python.org"]

    sha = "b" * 40
    client, git_asked = counting_client(
        {"https://api.github.com/repos/o/r/commits/HEAD": sha}
    )
    source = git_updates.GitSource("p", "https://github.com/o/r", "a" * 40)
    for _ in range(2):
        found = git_updates.find_git_updates(client, {"p": source}, cache=cache)
        assert found[0].latest == sha
    assert len(git_asked) == 1
