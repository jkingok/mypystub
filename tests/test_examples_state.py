"""Examples keep their own state in an object of their own, not on the toga.App.

The app object belongs to Toga and, when an example runs inside the launcher,
is shared with it. Attributes an example hangs on it can clash with another
user of the same name (once, ``app.settings`` replaced the launcher's own).
Examples are free to use Toga's features, such as the widget registry; this is
only about where they keep their own state.
"""

import ast
from pathlib import Path

EXAMPLES = Path(__file__).parent.parent / "src" / "mypystub" / "resources" / "examples"
APP_NAMES = {"app", "host_app"}
# Toga's own, documented settable attributes
TOGA_ATTRIBUTES = {"main_window"}


def is_app(node: ast.expr) -> bool:
    """Whether `node` is `app`, `host_app` or `self.app`."""
    if isinstance(node, ast.Name):
        return node.id in APP_NAMES
    return (
        isinstance(node, ast.Attribute)
        and node.attr in APP_NAMES
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    )


def test_examples_do_not_attach_state_to_the_app() -> None:
    """No ``app.<name> = ...`` apart from Toga's own attributes."""
    found = []
    for path in sorted(EXAMPLES.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            targets = (
                node.targets
                if isinstance(node, ast.Assign)
                else [node.target]
                if isinstance(node, (ast.AnnAssign, ast.AugAssign))
                else []
            )
            for target in targets:
                if (
                    isinstance(target, ast.Attribute)
                    and is_app(target.value)
                    and target.attr not in TOGA_ATTRIBUTES
                ):
                    found.append(f"{path.relative_to(EXAMPLES)}:{node.lineno}")
    assert not found, "state attached to the app: " + ", ".join(found)
