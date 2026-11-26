"""togax-jkingok: reusable Toga widgets, made for phones first.

A prototype of the package planned in MyPyStub issue #323. It lives inside
MyPyStub's repository until it has a repository of its own, so it must stand
alone: only the standard library, Toga and its backends, and the libraries those
backends use (Rubicon, Chaquopy's ``java``, PyGObject's ``gi`` and pythonnet's
``System``) may be imported, never ``mypystub`` (``tests/test_togax_standalone.py``
checks this). Platform code goes inside ``sys.platform`` checks.

Platform support:

- **Primary: iOS and Android.** Every widget does its whole job there.
- **Desktop (macOS, GTK, Windows): working.** Everything has a desktop
  fallback: widgets work, more plainly where a phone-only feature doesn't
  apply (SafeArea is then a plain Box), and services use the desktop's own
  (the clipboard reads and writes the system clipboard).
- **Web and Textual: limited or none,** but never broken on import.

Whatever the platform, ``import togax_jkingok`` (and each public module in it)
must succeed, even with no backend's native libraries installed
(``tests/test_togax_platforms.py`` imports it as each platform). A private
module (``_android_insets``, ``_ios_clipboard``, …) holds one platform's native
code, and is imported only on that platform, when it's needed.

Besides widgets, the package wraps platform services an app reaches through
its UI: :mod:`togax_jkingok.clipboard` reads and writes the clipboard.
"""

from . import clipboard
from .collapsible import Collapsible
from .editable_list import EditableList
from .labelled import LabelledActivity, LabelledProgress, LabelledSelection
from .layout import refresh_on_new_width, relayout, relayout_on_resize
from .orientation import OrientationBox
from .safe_area import Insets, SafeArea, SafeColumn

__all__ = [
    "Collapsible",
    "EditableList",
    "Insets",
    "LabelledActivity",
    "LabelledProgress",
    "LabelledSelection",
    "OrientationBox",
    "SafeArea",
    "SafeColumn",
    "clipboard",
    "refresh_on_new_width",
    "relayout",
    "relayout_on_resize",
]
