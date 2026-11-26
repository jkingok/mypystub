"""Debug logging from a stamp file in the cache folder (#347).

The stamp's presence turns debug lines on, read when the Prototype is built,
so the start of a launch is covered. Logging levels are restored after each test.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

from mypystub import logfile


@pytest.fixture
def restored() -> Iterator[None]:
    """Put stdout, stderr, logging and the app's levels back after the test."""
    saved = sys.stdout, sys.stderr, logfile._current, logging.lastResort
    levels = {n: logging.getLogger(n).level for n in logfile.APP_LOGGERS}
    handlers = list(logging.root.handlers)
    yield
    sys.stdout, sys.stderr, logfile._current, logging.lastResort = saved
    for name, level in levels.items():
        logging.getLogger(name).setLevel(level)
    logging.root.handlers[:] = handlers
    logfile._debugging = False


def start(tmp_path: Path) -> logfile.LogRedirector:
    """Install the log as the app does at launch, with no stamp applied yet.

    pytest puts its capture handlers on the root logger as each test body
    starts; the app has none, so records reach the handler of last resort.
    """
    logging.root.handlers[:] = []
    logfile._debugging = False
    redirector = logfile.install(tmp_path / "app_runtime.log")
    redirector.terminal = None
    return redirector


def logged(redirector: logfile.LogRedirector) -> str:
    redirector.flush()
    return redirector.path.read_text()


def test_debug_is_not_written_by_default_but_info_is(
    tmp_path: Path, restored: None
) -> None:
    clean = start(tmp_path)
    log = logging.getLogger("mypystub.test")
    log.debug("quiet detail")
    log.info("routine news")
    assert "routine news" in logged(clean)
    assert "quiet detail" not in logged(clean)


def test_the_stamp_in_the_cache_turns_debug_on(tmp_path: Path, restored: None) -> None:
    clean = start(tmp_path)
    cache = tmp_path / "cache"
    cache.mkdir()
    logfile.stamp_path(cache).touch()
    logfile.enable_debugging(logfile.stamp_path(cache).exists())
    logging.getLogger("mypystub.test").debug("written with the stamp")
    assert "written with the stamp" in logged(clean)


def test_turning_off_stops_debug(tmp_path: Path, restored: None) -> None:
    clean = start(tmp_path)
    logfile.enable_debugging(True)
    logfile.enable_debugging(False)
    logging.getLogger("mypystub.test").debug("after off")
    assert "after off" not in logged(clean)


def test_the_app_loggers_create_debug_records_but_others_do_not(
    tmp_path: Path, restored: None
) -> None:
    start(tmp_path)
    assert logging.getLogger("mypystub.x").isEnabledFor(logging.DEBUG)
    assert not logging.getLogger("some_library").isEnabledFor(logging.DEBUG)


def test_the_stamp_is_in_the_cache_folder(tmp_path: Path) -> None:
    assert logfile.stamp_path(tmp_path) == tmp_path / logfile.DEBUG_STAMP
