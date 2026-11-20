"""Setup's Environment screen: no intro note and no section to fold.

The Setup tab already has an Environment heading, and the screen's title is
"Environment", so the screen repeats neither. A script's own Setup form keeps
its foldable Arguments and Environment sections.
"""

from pathlib import Path
from typing import Any

import toga

from mypystub import ui
from tests.support_ui import row


def walk(widget: Any) -> list[Any]:
    """`widget` and everything inside it, scroll containers included."""
    found, pending = [], [widget]
    while pending:
        current = pending.pop()
        found.append(current)
        if isinstance(current, toga.ScrollContainer) and current.content is not None:
            pending.append(current.content)
        pending.extend(getattr(current, "children", None) or [])
    return found


def test_setup_environment_has_no_note_or_heading(
    proto: ui.Prototype, config: Path
) -> None:
    form = proto.open_setup_environment()
    widgets = walk(form.content)
    labels = [w.text for w in widgets if isinstance(w, toga.Label)]
    assert not any("inherits these variables" in text for text in labels)
    switches = [w.text for w in widgets if isinstance(w, toga.Switch)]
    assert not any(text.startswith("Environment") for text in switches)
    assert form.sections == {}
    assert form.env_list in widgets  # the variables are still listed
    form.done()


def test_a_scripts_form_keeps_its_folding_sections(
    proto: ui.Prototype, config: Path
) -> None:
    form = proto.open_run_with(row(proto, "top"))
    assert set(form.sections) == {"args", "env", "workdir"}
    assert form.sections["env"][0].text.startswith("Environment")
    form.done()
