"""Runs work in the chosen folder: Examples in the cache, inherited from category Setup (#308)."""

from pathlib import Path

import pytest
import toga

from mypystub import ui, workdirs
from mypystub.run_settings import RunSettings
from tests.support_ui import row, run, tap, wait_for

SCRIPT = (
    "import os, pathlib\n"
    "print('cwd', os.getcwd())\n"
    "print('file', pathlib.Path(__file__).parent)\n"
    "open('out.txt', 'w').write('written')\n"
    "open('out.log', 'a').write('appended')\n"
)


@pytest.fixture
def examples(
    proto: ui.Prototype, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """A read-only stand-in for the bundled Examples, holding fancy.py."""
    folder = tmp_path / "examples"
    folder.mkdir()
    (folder / "fancy.py").write_text(SCRIPT)
    folder.chmod(0o555)  # read-only, as in the app bundle
    monkeypatch.setattr(proto, "examples_path", folder)
    yield folder
    folder.chmod(0o755)


def output(proto: ui.Prototype, label: str) -> str:
    line = next(
        line for line in proto.print_text.value.splitlines() if line.startswith(label)
    )
    return line.split(" ", 1)[1]


def run_in(proto: ui.Prototype, app: toga.App, category: str, title: str, mp) -> None:
    proto.show_category(category)
    proto.reload_menu(proto.script_list)
    tap(proto, title, mp, app)
    wait_for(app, lambda: proto.ended_run == proto.run_id)


def test_an_example_runs_in_its_cache_folder(
    proto: ui.Prototype, app: toga.App, examples: Path, config: Path, monkeypatch
) -> None:
    """fancy.py writes and appends relative files without changing the example."""
    import shutil

    expected = Path(proto.cache_path) / "workdirs" / "Examples" / "fancy.py"
    shutil.rmtree(expected, ignore_errors=True)  # the cache outlives a run
    run_in(proto, app, "Examples", "fancy", monkeypatch)
    cwd = Path(output(proto, "cwd"))
    assert cwd == expected
    assert (cwd / "out.txt").read_text() == "written"
    assert (cwd / "out.log").read_text() == "appended"
    assert Path(output(proto, "file")) == examples  # __file__ is unchanged
    assert proto.script_activity.text.text  # it ran to the end
    assert not (examples / "out.txt").exists()


def test_a_documents_script_runs_in_its_own_folder(
    proto: ui.Prototype, app: toga.App, docs: Path, config: Path, monkeypatch
) -> None:
    (docs / "mine.py").write_text(SCRIPT)
    run_in(proto, app, "Documents", "mine", monkeypatch)
    assert Path(output(proto, "cwd")) == docs
    assert (docs / "out.txt").exists()


def test_a_category_choice_is_inherited_and_a_scripts_own_wins(
    proto: ui.Prototype, app: toga.App, docs: Path, config: Path, monkeypatch
) -> None:
    (docs / "out").mkdir()
    (docs / "mine.py").write_text(SCRIPT)
    proto.settings.set_run_with(
        proto.category_key("Documents"),
        RunSettings(workdir=workdirs.documents("out")),
        with_args=False,
    )
    run_in(proto, app, "Documents", "mine", monkeypatch)
    assert Path(output(proto, "cwd")) == docs / "out"
    assert "· in Documents › out" not in proto.script_activity.text.text  # ended

    proto.settings.set_run_with(
        proto.row_key(row(proto, "mine")), RunSettings(workdir=workdirs.SCRIPT)
    )
    run_in(proto, app, "Documents", "mine", monkeypatch)
    assert Path(output(proto, "cwd")) == docs


def test_the_form_shows_and_changes_the_folder(
    proto: ui.Prototype, app: toga.App, docs: Path, config: Path, monkeypatch
) -> None:
    (docs / "mine.py").write_text("print(1)\n")
    proto.reload_menu(proto.script_list)
    form = proto.open_run_with(row(proto, "mine"))
    assert form.workdir_text() == "Script's folder (from the default)"

    async def choose(current: str | None) -> tuple[bool, str | None]:
        return True, workdirs.CACHE

    form.pick_workdir = choose
    run(app, form.change_workdir())
    assert form.workdir_label.text == "Cache"
    saved = proto.settings.get_run_with(proto.row_key(row(proto, "mine")))
    assert saved.workdir == workdirs.CACHE
    form.done()


def test_the_picker_offers_cache_without_browsing_it_and_documents_folders(
    proto: ui.Prototype, app: toga.App, docs: Path, config: Path
) -> None:
    (docs / "data" / "out").mkdir(parents=True)
    (docs / "backups").mkdir()
    task = app.loop.create_task(proto.pick_workdir(None))
    run(app, __import__("asyncio").sleep(0))
    screen = app.main_window.content
    rows_list = next(w for w in walk(screen) if isinstance(w, toga.DetailedList))
    titles = [r.title for r in rows_list.data]
    assert titles[:3] == ["Inherit", "Script's folder", "Cache"]
    assert "data ›" in titles and "backups ›" not in titles
    rows_list._impl._set_value("selection", titles.index("data ›"))
    rows_list.on_select()  # type: ignore[misc]
    assert [r.title for r in rows_list.data][:2] == ["..", "out ›"]
    use = next(
        w
        for w in walk(screen)
        if isinstance(w, toga.Button) and w.text.startswith("Use ")
    )
    use.on_press()  # type: ignore[misc]
    assert run(app, task) == (True, "documents:data")


def walk(widget):
    found, pending = [], [widget]
    while pending:
        current = pending.pop()
        found.append(current)
        pending.extend(getattr(current, "children", None) or [])
        content = getattr(current, "content", None)
        if isinstance(content, toga.Widget):
            pending.append(content)
    return found
