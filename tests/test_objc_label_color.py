"""UIColor.labelColor is a property, here and in anything a script shares it with.

Rubicon ignores ``declare_class_property`` for a method that has been called, so
one ``UIColor.labelColor()`` leaves it a method for the rest of the process. The
launcher runs first, so that broke toga-console's iOS backend (#180).
"""

from pathlib import Path

import mypystub

SRC = Path(mypystub.__file__).parent


def test_label_color_is_never_called() -> None:
    """Use ``UIColor.labelColor``, after declaring it, not ``labelColor()``."""
    offenders = [
        str(path.relative_to(SRC))
        for path in sorted(SRC.rglob("*.py"))
        if "UIColor.labelColor(" in path.read_text(encoding="utf-8")
    ]
    assert not offenders, offenders
