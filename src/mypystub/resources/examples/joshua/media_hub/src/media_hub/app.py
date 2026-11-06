"""
A Toga demonstration that generates a media catalog using themoviedb.org targeting iOS.
"""

import toga

from . import ui
from .state import state


class MyApp(toga.App):
    def startup_into(app):
        """Construct and show the Toga application.

        Usually, you would add your application to a main content box.
        We then create a main window (with a name matching the app), and
        show the main window.
        """
        state.proto = ui.Prototype(
            host_app=app, on_done=lambda _: MyApp.unstack_from(app)
        )

        # Update window context and inject the prototype layout
        t = getattr(state.proto, "title", app.formal_name)
        if not app.main_window:
            app.main_window = toga.MainWindow(title=t)
        mw = app.main_window
        if mw.content:  # pyright: ignore[reportAttributeAccessIssue]
            if not hasattr(mw, "content_stack"):
                mw.content_stack = []  # pyright: ignore[reportAttributeAccessIssue]
            mw.content_stack.append((mw.title, mw.content))  # pyright: ignore[reportAttributeAccessIssue]
        mw.title = t  # pyright: ignore[reportAttributeAccessIssue]
        mw.content = state.proto.get_content()  # pyright: ignore[reportAttributeAccessIssue]
        if not mw.visible:  # pyright: ignore[reportAttributeAccessIssue]
            mw.show()  # pyright: ignore[reportAttributeAccessIssue]

    def unstack_from(app):
        if (
            hasattr(app.main_window, "content_stack")
            and len(app.main_window.content_stack) > 0  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
        ):
            t, c = app.main_window.content_stack.pop()  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]
            app.main_window.title = t  # pyright: ignore[reportOptionalMemberAccess]
            app.main_window.content = c  # pyright: ignore[reportAttributeAccessIssue, reportOptionalMemberAccess]

    def startup(self):
        return MyApp.startup_into(self)


def main():
    if not (a := toga.App.app):
        return MyApp()
    elif a.loop:
        a.loop.call_soon(lambda a=a: MyApp.startup_into(a))  # pyright: ignore[reportArgumentType]
    else:
        MyApp.startup_into(a)  # pyright: ignore[reportArgumentType]
    return None


if __name__ == "__main__":
    main()
