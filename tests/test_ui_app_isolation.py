"""The launcher keeps its state on itself, never on the shared app (or its registry).

Prototypes run in the launcher's process and share the Toga app object. A
prototype that sets ``app.settings`` or reuses a widget id once broke the
launcher; these guard against reading launcher state back from the app.
"""

import ast
from pathlib import Path

SRC = Path(__file__).parent.parent / "src" / "mypystub"
# Where launcher code may touch the app object: Toga's own, documented API
ALLOWED_APP_ATTRIBUTES = {
    "main_window",
    "paths",
    "loop",
    "formal_name",
    "app_id",
    "icon",
    "version",
    "commands",
    "on_exit",
    "user_documents_dir",
    "add_background_task",
    "current_window",
    "windows",
    "about",
    "visit_homepage",
    "home_page",
}


def app_attribute_uses() -> set[tuple[str, str]]:
    """(file, attribute) for each ``self.app.<attribute>`` in the launcher."""
    found: set[tuple[str, str]] = set()
    for path in SRC.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if (
                isinstance(node, ast.Attribute)
                and isinstance(node.value, ast.Attribute)
                and node.value.attr == "app"
                and isinstance(node.value.value, ast.Name)
                and node.value.value.id == "self"
            ):
                found.add((path.name, node.attr))
    return found


def test_launcher_only_uses_toga_api_on_the_app() -> None:
    """``self.app.<x>`` is Toga's API; launcher state lives on the launcher."""
    unknown = sorted(
        f"{file}: app.{name}"
        for file, name in app_attribute_uses()
        if name not in ALLOWED_APP_ATTRIBUTES
    )
    assert not unknown, "launcher state read from the shared app: " + ", ".join(unknown)


def test_launcher_does_not_use_the_widget_registry() -> None:
    """Widget ids are global; the launcher holds references instead."""
    ids = [
        f"{path.name}:{node.lineno}"
        for path in SRC.glob("*.py")
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8")))
        if isinstance(node, ast.keyword) and node.arg == "id"
    ]
    assert not ids, "widget ids set in the launcher: " + ", ".join(ids)
