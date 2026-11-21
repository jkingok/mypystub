"""The update check reports each package as it asks PyPI, so it can be counted."""

import httpx2

from mypystub import maintenance as m


def test_find_updates_reports_each_package_before_asking() -> None:
    asked: list[str] = []
    seen: list[str] = []

    def handler(request: httpx2.Request) -> httpx2.Response:
        asked.append(request.url.path.split("/")[2])
        assert seen[-1] == asked[-1]  # reported before its request
        return httpx2.Response(404)

    client = httpx2.Client(transport=httpx2.MockTransport(handler))
    m.find_updates(client, {"b": "1.0", "a": "1.0"}, on_check=seen.append)
    assert seen == asked == ["a", "b"]
