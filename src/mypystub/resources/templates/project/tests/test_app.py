"""App Template's tests: ``briefcase dev --test`` runs them.

Add tests of your own app's logic here.
"""

from app_template import app  # pyright: ignore[reportMissingImports]


def test_the_app_has_a_main() -> None:
    """The bootstrap (and MyPyStub) start the app by calling its main()."""
    assert callable(app.main)
