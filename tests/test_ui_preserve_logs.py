"""The Preserve Logs switch: the log is emptied at launch unless it is on (#198).

Skipped where toga_dummy isn't installed, such as on device.
"""

import io
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import logfile, ui


@pytest.fixture
def log(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> logfile.LogRedirector:
    """An installed-looking redirector with some history in it."""
    redirector = logfile.LogRedirector(tmp_path / "app.log", terminal=io.StringIO())
    redirector.write("old line\n")
    redirector.flush()
    monkeypatch.setattr(logfile, "_current", redirector)
    return redirector


def test_preserve_logs_is_off_by_default(proto: ui.Prototype, config: Path) -> None:
    """A user who never touches it gets a fresh log each launch."""
    assert proto.preserve_logs is False


def test_with_it_off_the_launch_empties_the_log(
    proto: ui.Prototype, config: Path, log: logfile.LogRedirector
) -> None:
    """Truncate rather than append."""
    proto.apply_log_policy()
    assert log.log_path.read_text() == ""
    log.write("new line\n")
    log.flush()
    assert log.log_path.read_text() == "new line\n"


def test_with_it_on_the_launch_keeps_the_log(
    proto: ui.Prototype, config: Path, log: logfile.LogRedirector
) -> None:
    """Appending is what it was."""
    proto.set_preserve_logs(True)
    proto.apply_log_policy()
    assert log.log_path.read_text() == "old line\n"


def test_without_a_redirector_there_is_nothing_to_do(
    proto: ui.Prototype, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Development runs and tests have no log redirector."""
    monkeypatch.setattr(logfile, "_current", None)
    proto.apply_log_policy()


def test_a_malformed_setting_means_off(proto: ui.Prototype, config: Path) -> None:
    """Anything but a true/false in launcher.toml is the default."""
    config.write_text('preserve_logs = "yes"\n')
    proto.settings.config_doc = proto.settings._load()
    assert proto.preserve_logs is False


def test_the_setup_switch_reads_and_writes_the_setting(
    proto: ui.Prototype, config: Path
) -> None:
    """A switch in the Setup menu, off to begin with."""
    switches: list[toga.Switch] = []

    def walk(widget: toga.Widget) -> None:
        if isinstance(widget, toga.Switch):
            switches.append(widget)
        for child in widget.children:
            walk(child)

    for widget in proto.setup_sections():
        walk(widget)
    (switch,) = [s for s in switches if s.text == "Preserve Logs"]
    assert switch.value is False
    proto.handle_preserve_logs_toggle(SimpleNamespace(value=True))  # type: ignore[arg-type]
    assert proto.preserve_logs is True
    proto.handle_preserve_logs_toggle(SimpleNamespace(value=False))  # type: ignore[arg-type]
    assert proto.preserve_logs is False
