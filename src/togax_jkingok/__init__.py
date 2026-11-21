"""togax-jkingok: reusable Toga widgets, made for phones first.

A prototype of the package planned in MyPyStub issue #323. It lives inside
MyPyStub's repository until it has a repository of its own, so it must stand
alone: only the standard library, Toga and its backends, Rubicon and Chaquopy's
``java`` may be imported, never ``mypystub`` (``tests/test_togax_standalone.py``
checks this). Platform code goes inside ``sys.platform`` checks.

Platform support:

- **Primary: iOS and Android.** Every widget does its whole job there.
- **Desktop (macOS, GTK, Windows): working.** Widgets work, more plainly where
  a phone-only feature doesn't apply (SafeArea is then a plain Box).
- **Web and Textual: limited or none,** but never broken on import.

Whatever the platform, ``import togax_jkingok`` (and each module in it) must
succeed, even with no backend's native libraries installed
(``tests/test_togax_platforms.py`` imports it as each platform).
"""

from .collapsible import Collapsible
from .labelled import LabelledActivity, LabelledProgress, LabelledSelection
from .layout import refresh_on_new_width, relayout, relayout_on_resize
from .orientation import OrientationBox

__all__ = [
    "Collapsible",
    "LabelledActivity",
    "LabelledProgress",
    "LabelledSelection",
    "OrientationBox",
    "refresh_on_new_width",
    "relayout",
    "relayout_on_resize",
]
