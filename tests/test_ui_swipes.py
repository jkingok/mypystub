"""UI tests for the swipe actions (Info, Setup) and packages with several entry points.

Skipped where toga_dummy isn't installed, such as on device.
"""

import asyncio
import os
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

pytest.importorskip("toga_dummy")
os.environ["TOGA_BACKEND"] = "toga_dummy"

import toga

from mypystub import ui
from tests.support_ui import (
    ICONS,
    press,
    row,
    run,
    run_to_end,
    select,
    tap,
    titles,
    wait_for,
)

# Swipe actions: Info and Setup (#59)
# ---------------------------------------------------------------------------


Prompt = tuple[str, list[tuple[str, str]]]


def show_inherited(form: Any) -> None:
    """Switch on the listing of inherited variables, as the user would."""
    assert form.inherited_switch is not None
    form.inherited_switch.value = True
    form._toggle_inherited(form.inherited_switch)


def script_prompts(form: Any, *answers: list[str] | None) -> list[Prompt]:
    """Answer `form`'s next prompts with `answers` (None cancels).

    Returns what was asked. The form keeps the prompt it was opened with, so
    it is replaced on the form itself.

    Each asked prompt is recorded as (title, [(label, starting text), ...]).
    """
    asked: list[Prompt] = []
    queue = list(answers)

    async def ask_fields(
        title: str, message: str, fields: list[Any], ok: str = "Done"
    ) -> list[str] | None:
        asked.append((title, [(f.label, f.value) for f in fields]))
        return queue.pop(0)

    form.ask_fields = ask_fields
    return asked


def test_launcher_list_has_info_and_run_with_swipes(proto: ui.Prototype) -> None:
    """Swipe left is Info and swipe right is Setup, on every row."""
    assert proto.script_list._primary_action == "Info"
    assert proto.script_list._secondary_action == "Setup"


def test_swipes_on_rows_that_cannot_run_say_why(
    proto: ui.Prototype, app: toga.App, messages: list[tuple]
) -> None:
    """Folders and ".." explain, by name, why there's nothing to show or run."""
    proto.handle_run_with(proto.script_list, row=row(proto, "a"))
    run(app, asyncio.sleep(0.01))
    assert messages[-1] == (
        "a",
        (
            "a is a folder, so there's nothing to run. Open it and swipe a script "
            "or project inside."
        ),
    )
    run(app, proto.show_info(row(proto, "a")))
    assert messages[-1] == (
        "a",
        "a has no README to show. It holds 1 subfolder. Add a README.md to describe it.",
    )
    run(app, proto.show_info(row(proto, "..")))
    assert messages[-1][1] == (
        "This row goes back to the categories, so there's nothing to describe."
    )
    run(app, proto.run_with(row(proto, "..")))
    assert messages[-1][1] == (
        "This row goes back to the categories, so there's nothing to run."
    )


def test_up_rows_name_the_folder_they_lead_to(
    proto: ui.Prototype, app: toga.App, messages: list[tuple]
) -> None:
    """Deeper down, ".." names its destination."""
    proto.subfolder = Path("a/b")
    proto.reload_menu(proto.script_list)
    run(app, proto.run_with(row(proto, "..")))
    assert (
        messages[-1][1]
        == "This row goes back to Documents/a, so there's nothing to run."
    )


def test_category_swipes(
    proto: ui.Prototype, app: toga.App, messages: list[tuple]
) -> None:
    """Categories can't run; Examples has a README, Documents here has none."""
    proto.show_category(None)
    proto.reload_menu(proto.script_list)
    run(app, proto.run_with(row(proto, "Documents")))
    assert messages[-1][1].startswith("Documents holds your own scripts and projects.")
    run(app, proto.show_info(row(proto, "Documents")))
    assert "Documents has no README to show." in messages[-1][1]

    tabs = app.main_window.content
    run(app, proto.show_info(row(proto, "Examples")))
    assert app.main_window.title == "Examples"
    # The README's "# Examples" only repeats the title bar, so it's dropped
    assert "<h1>Examples</h1>" not in proto.readme_page
    assert "<p>" in proto.readme_page
    proto.pop_screen()
    assert app.main_window.content is tabs


def test_folder_readme_is_shown_safely(
    proto: ui.Prototype, app: toga.App, docs: Path, messages: list[tuple]
) -> None:
    """A folder's README opens on its own screen, without its raw HTML."""
    (docs / "a" / "README.md").write_text("# About a\n\n<script>alert(1)</script>\n")
    tabs = app.main_window.content
    run(app, proto.show_info(row(proto, "a")))
    assert messages == []
    assert app.main_window.title == "a"
    page = proto.readme_page
    assert "<h1>About a</h1>" in page and "<script>alert" not in page
    assert proto.open_external(proto.readme_view, "about:blank") is True
    proto.pop_screen()
    proto.pop_screen()  # a double tap pops nothing more
    assert app.main_window.content is tabs


def test_script_info_page(
    proto: ui.Prototype, app: toga.App, messages: list[tuple]
) -> None:
    """Info on a script opens its page: docstring, dependencies, source."""
    tabs = app.main_window.content
    run(app, proto.show_info(row(proto, "top")))
    assert messages == []
    assert app.main_window.title == "top"
    page = proto.readme_page
    assert "<h1>top</h1>" not in page  # the title bar already says "top"
    assert "<p>At the top.</p>" in page
    assert "<h2>Source</h2>" in page and "top.py, 1 line." in page
    assert str(proto.data_path) not in page  # no local paths
    proto.pop_screen()
    assert app.main_window.content is tabs


def test_run_with_form_edits_arguments(
    proto: ui.Prototype, app: toga.App, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Add, select, move, edit and delete arguments; buttons follow the selection."""
    tabs = app.main_window.content
    form = proto.open_run_with(row(proto, "top"))
    assert app.main_window.title == "Setup · top"
    assert not form.arg_buttons["edit"].enabled
    asked = script_prompts(form, ["--name"], ["Ada"], ["x"], ["Ada Lovelace"], None)
    for _ in range(3):
        run(app, form.add_arg())
    assert asked[0] == ("Add argument", [("Argument", "")])
    assert form.args == ["--name", "Ada", "x"]
    assert form.arg_index == 2  # the new row is selected
    assert [r.subtitle for r in form.args_list.data] == [
        "Argument 1",
        "Argument 2",
        "Argument 3",
    ]

    select(form.args_list, form._arg_selected, 0)
    enabled = {w: b.enabled for w, b in form.move_buttons.items()}
    assert enabled == {"top": False, "up": False, "down": True, "bottom": True}
    press(app, form.move_buttons["bottom"])
    assert form.args == ["Ada", "x", "--name"] and form.arg_index == 2
    press(app, form.move_buttons["up"])
    assert form.args == ["Ada", "--name", "x"] and form.arg_index == 1
    press(app, form.move_buttons["top"])
    assert form.args == ["--name", "Ada", "x"] and form.arg_index == 0

    select(form.args_list, form._arg_selected, 1)
    press(app, form.arg_buttons["edit"])
    assert asked[-1] == ("Edit argument", [("Argument", "Ada")])
    assert form.args == ["--name", "Ada Lovelace", "x"]
    run(app, form.edit_arg())  # cancelled: nothing changes
    assert form.args == ["--name", "Ada Lovelace", "x"]
    press(app, form.arg_buttons["delete"])
    assert form.args == ["--name", "x"] and form.arg_index is None
    assert not form.arg_buttons["delete"].enabled

    form.done()
    assert app.main_window.content is tabs
    # Every change was saved as it was made
    assert proto.settings.get_run_with("Documents/top.py").args == ["--name", "x"]


def test_run_with_form_environment_is_sorted_and_inherits_setup(
    proto: ui.Prototype, app: toga.App, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Variables stay A–Z; Setup's show as inherited and can be overridden."""
    proto.settings.set_environment({"GREETING": "Hello"})
    form = proto.open_run_with(row(proto, "top"))
    assert len(form.env_list.data) == 0  # inherited variables start hidden
    show_inherited(form)
    assert [(r.title, r.subtitle) for r in form.env_list.data] == [
        ("GREETING", "from Setup · Hello")
    ]
    select(form.env_list, form._env_selected, 0)
    assert form.env_buttons["edit"].enabled
    assert not form.env_buttons["delete"].enabled  # it's set in Setup
    assert "set in Setup" in form.env_note.text

    asked = script_prompts(form, ["GREETING", "Hi"], ["zed", ""], ["Alpha", ""])
    press(app, form.env_buttons["edit"])  # override it here
    assert asked[0] == ("Edit variable", [("Name", "GREETING"), ("Value", "Hello")])
    for _ in range(2):
        run(app, form.add_env())
    assert [(r.title, r.subtitle) for r in form.env_list.data] == [
        ("Alpha", "(empty)"),
        ("GREETING", "Hi"),
        ("zed", "(empty)"),
    ]

    select(form.env_list, form._env_selected, 1)
    assert "overrides an inherited value" in form.env_note.text
    press(app, form.env_buttons["delete"])  # the inherited value is back
    assert form.env == {"zed": "", "Alpha": ""}
    assert form.env_list.data[1].subtitle == "from Setup · Hello"


def test_run_with_form_refuses_bad_names(
    proto: ui.Prototype, app: toga.App, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Bad names ask again with what was typed; replacing a name asks first."""
    told: list[tuple[str, str]] = []
    answers: list[bool] = [False]

    async def tell(title: str, text: str) -> None:
        told.append((title, text))

    async def ask(title: str, text: str) -> bool:
        return answers.pop(0)

    monkeypatch.setattr(proto, "tell", tell)
    monkeypatch.setattr(proto, "ask", ask)
    form = proto.open_run_with(row(proto, "top"))
    bad_names = ["A=B", "MY VAR", "1ST", "my-var"]
    asked = script_prompts(
        form,
        *([[bad, "v"] for bad in bad_names]),
        ["A", "x\0y"],
        ["A", "1"],
    )
    run(app, form.add_env())
    assert [t[0] for t in told[:4]] == ["Variable name"] * 4
    assert asked[1][1] == [("Name", "A=B"), ("Value", "v")]  # kept what was typed
    assert told[-1][0] == "Variable value" and "NUL" in told[-1][1]
    assert form.env == {"A": "1"}

    script_prompts(form, ["A", "2"], None)
    run(app, form.add_env())  # "Replace?" answered no, then cancelled
    assert form.env == {"A": "1"}


def test_setup_form_saves_as_you_go_and_done_never_runs(
    proto: ui.Prototype, app: toga.App, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each change is saved straight away; Done only closes, it doesn't run."""
    runs: list[Any] = []

    async def run_row(r: Any) -> None:
        runs.append(r.title)

    monkeypatch.setattr(proto, "run_row", run_row)
    form = proto.open_run_with(row(proto, "top"))
    assert "run_with" not in config.read_text()  # opening saves nothing
    script_prompts(form, ["one"], ["B", "2"], None)
    run(app, form.add_arg())
    assert proto.settings.get_run_with("Documents/top.py").args == ["one"]
    run(app, form.add_env())
    assert proto.settings.get_run_with("Documents/top.py").env == {"B": "2"}

    run(app, form.add_arg())  # cancelled: the typing is dropped
    assert proto.settings.get_run_with("Documents/top.py").args == ["one"]

    form.done()
    run(app, asyncio.sleep(0.01))
    assert runs == []
    form = proto.open_run_with(row(proto, "top"))
    assert (form.args, form.env) == (["one"], {"B": "2"})
    form.done()


def test_tap_runs_with_saved_arguments_and_inherited_environment(
    proto: ui.Prototype,
    app: toga.App,
    docs: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tap passes the saved argv, and Setup's variables under the script's own."""
    from mypystub.run_settings import RunSettings

    proto.settings.set_environment({"GREETING": "Hello", "WHO": "world"})
    proto.settings.set_run_with(
        "Documents/case.py", RunSettings(["--loud", "two words"], {"WHO": "Ada"})
    )
    source = (
        "import os, sys\n"
        "print(sys.argv[1:])\n"
        "print(os.environ['GREETING'], os.environ['WHO'])\n"
    )
    run_to_end(proto, app, docs, source, monkeypatch)
    assert proto.print_text.value == "['--loud', 'two words']\nHello Ada\n"
    assert "WHO" not in os.environ  # restored after the run


def test_setup_environment_page(
    proto: ui.Prototype, app: toga.App, config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The Setup tab's Environment page edits variables only, saving as it goes."""
    form = proto.open_setup_environment()
    assert not form.with_args
    assert app.main_window.title == "Environment"
    script_prompts(form, ["GREETING", "Hello"])
    run(app, form.add_env())
    assert proto.settings.get_environment() == {"GREETING": "Hello"}
    form.done()


def test_setup_forms_finish_with_done(proto: ui.Prototype, config: Path) -> None:
    """Changes save as they're made, so there's no Save button; a runnable
    row also offers Make Quick Start, and the environment form just Done."""
    expected = {
        proto.open_run_with(row(proto, "top")): ["Make Quick Start", "Done"],
        proto.open_setup_environment(): ["Done"],
    }
    for form, want in expected.items():
        buttons = [
            w.text
            for w in form.content.children[-1].children
            if isinstance(w, toga.Button)
        ]
        assert buttons == want
        form.done()


def test_run_with_toolbars_use_spaced_symbols(
    proto: ui.Prototype, config: Path
) -> None:
    """Toolbar buttons are symbols, to fit a phone, with space between them."""
    form = proto.open_run_with(row(proto, "top"))

    def labels(box: toga.Widget) -> list[str]:
        return [w.text for w in box.children if isinstance(w, toga.Button)]

    args_header, _, _, move_row, env_header = form.content.children[:5]
    assert labels(args_header) == ["+", "✎", "⌫"]
    assert labels(env_header) == ["+", "✎", "⌫", "⊘", "ⓘ"]  # ⊘ unsets, ⓘ shows it all
    assert labels(move_row) == ["⤒", "↑", "↓", "⤓"]
    for button in args_header.children[1:] + env_header.children[1:]:
        assert button.style.margin_left > 0 and button.style.margin_right > 0
    form.done()


def test_lists_keep_their_selection_when_the_form_reappears(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On iOS, a reappearing table must not clear the highlighted row."""
    from mypystub import run_with

    native_controller = SimpleNamespace(clearsSelectionOnViewWillAppear=True)
    widget = SimpleNamespace(_impl=SimpleNamespace(native_controller=native_controller))
    run_with.keep_selection(widget)  # type: ignore[arg-type]
    assert native_controller.clearsSelectionOnViewWillAppear  # not iOS: untouched
    monkeypatch.setattr(run_with.sys, "platform", "ios")
    run_with.keep_selection(widget)  # type: ignore[arg-type]
    assert native_controller.clearsSelectionOnViewWillAppear is False


# ---------------------------------------------------------------------------
# Packages with several entry points (#94)
# ---------------------------------------------------------------------------

TOOLS_PYPROJECT = """
[project]
name = "tools"
description = "Some tools"

[project.scripts]
echo = "tools.cli:echo"

[project.gui-scripts]
window = "tools.cli:echo"

[project.entry-points."tools.plugins"]
value = "tools.cli:VALUE"
"""

TOOLS_CLI = """
import os
import sys

VALUE = 42


def echo():
    print(sys.argv)
    print(os.environ.get("GREETING"), os.environ.get("WHO"), os.environ.get("LEVEL"))
"""


@pytest.fixture
def tools(docs: Path, proto: ui.Prototype) -> Path:
    """A package with console, GUI and plugin entry points in Documents."""
    project = docs / "tools"
    (project / "src" / "tools").mkdir(parents=True)
    (project / "pyproject.toml").write_text(TOOLS_PYPROJECT)
    (project / "src" / "tools" / "__init__.py").write_text("")
    (project / "src" / "tools" / "cli.py").write_text(TOOLS_CLI)
    proto.reload_menu(proto.script_list)
    return project


def test_package_opens_like_a_folder_of_entry_points(
    proto: ui.Prototype, app: toga.App, tools: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Tapping the package lists its entry points; ".." goes back."""
    assert titles(proto) == ["..", "a", "tools", "top"]
    assert row(proto, "tools").kind == "package"
    tap(proto, "tools", monkeypatch, app)
    assert titles(proto) == ["..", "echo", "value", "window"]
    assert [r.subtitle for r in proto.script_list.data] == [
        "Back to Documents",
        "Console · tools.cli:echo",
        "tools.plugins · tools.cli:VALUE",
        "GUI · tools.cli:echo",
    ]
    tap(proto, "..", monkeypatch, app)
    assert titles(proto) == ["..", "a", "tools", "top"]


def test_package_and_entry_icons_are_placeholders_until_added(
    proto: ui.Prototype,
    app: toga.App,
    tools: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """boxes, terminal, window and plug icons show once their files exist."""
    icons = tmp_path / "icons"
    icons.mkdir()
    proto.icon_path = icons
    proto.reload_menu(proto.script_list)
    assert row(proto, "tools").icon is None
    tap(proto, "tools", monkeypatch, app)
    assert all(r.icon is None for r in proto.script_list.data)

    for name in ("boxes.png", "terminal.png", "window.png", "plug.png"):
        shutil.copy(ICONS / "list.png", icons / name)
    proto.reload_menu(proto.script_list)
    assert all(isinstance(r.icon, toga.Image) for r in proto.script_list.data[1:])
    proto.package_dir = None
    proto.reload_menu(proto.script_list)
    assert isinstance(row(proto, "tools").icon, toga.Image)


def test_package_info_lists_its_entry_points(
    proto: ui.Prototype,
    app: toga.App,
    tools: Path,
    messages: list[tuple],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Info on a package lists entries; on an entry it names the package."""
    run(app, proto.show_info(row(proto, "tools")))
    assert "<h2>Entry points</h2>" in proto.readme_page
    assert "<code>echo</code>: Console · <code>tools.cli:echo</code>" in (
        proto.readme_page
    )
    proto.pop_screen()
    tap(proto, "tools", monkeypatch, app)
    run(app, proto.show_info(row(proto, "echo")))
    page = proto.readme_page
    assert "An entry point of tools: <code>echo</code>: Console" in page
    assert "<h2>Entry points</h2>" not in page
    proto.pop_screen()
    run(app, proto.run_with(row(proto, "..")))
    assert (
        messages[-1][1] == "This row goes back to Documents, so there's nothing to run."
    )


def test_package_setup_sets_inherited_variables_only(
    proto: ui.Prototype, app: toga.App, tools: Path, config: Path
) -> None:
    """A package's Setup has no arguments; its variables save as they change."""
    run(app, proto.run_with(row(proto, "tools")))
    form = proto.run_with_form
    assert not form.with_args
    assert app.main_window.title == "Setup · tools"
    form.env = {"WHO": "Ada"}
    form.changed()
    form.done()
    from mypystub.run_settings import RunSettings

    assert proto.settings.get_run_with("Documents/tools") == RunSettings(
        [], {"WHO": "Ada"}
    )
    assert "args" not in proto.settings.get_table("run_with")["Documents/tools"]


def test_entry_inherits_setup_then_package_then_its_own(
    proto: ui.Prototype,
    app: toga.App,
    tools: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An entry point's form and run layer Setup, its package, then its own."""
    from mypystub.run_settings import RunSettings

    proto.settings.set_environment({"GREETING": "Hello", "WHO": "world", "LEVEL": "1"})
    proto.settings.set_run_with("Documents/tools", RunSettings([], {"WHO": "Ada"}))
    proto.settings.set_run_with(
        "Documents/tools:echo", RunSettings(["--loud"], {"LEVEL": "2"})
    )
    tap(proto, "tools", monkeypatch, app)
    form = proto.open_run_with(row(proto, "echo"))
    show_inherited(form)
    assert [(r.title, r.subtitle) for r in form.env_list.data] == [
        ("GREETING", "from Setup · Hello"),
        ("LEVEL", "2"),
        ("WHO", "from tools · Ada"),
    ]
    assert form.args == ["--loud"]
    form.done()

    tap(proto, "echo", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    assert proto.print_text.value == "['echo', '--loud']\nHello Ada 2\n"


def test_entry_that_cannot_run_says_why(
    proto: ui.Prototype,
    app: toga.App,
    tools: Path,
    config: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-callable entry point gets a "Can't Run" dialog, not a traceback."""
    tap(proto, "tools", monkeypatch, app)
    tap(proto, "value", monkeypatch, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)
    title, text, _, _ = proto.dialogs[-1]  # type: ignore[attr-defined]
    assert title == "Can't Run"
    assert text == "tools.cli:VALUE is an int, not something that can run."
