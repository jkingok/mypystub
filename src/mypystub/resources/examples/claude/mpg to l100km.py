# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "toga",
# ]
# ///
# Unit converter: miles per US gallon <-> litres per 100 km.
#
# Runs inside the MyPyStub app. It stacks its layout onto the existing main
# window, using the same content_stack as the launcher, and holds the script
# open with a threading.Event until the Back button restores the previous view.
import threading

import toga
from toga.style import Pack

# US gallon: 1 mile = 1609.344 m, 1 US gallon = 3.785411784 L
# L/100km = 235.215 / mpg
MPG_TO_L100 = 235.215


def mpg_to_l100km(mpg):
    if mpg <= 0:
        raise ValueError("mpg must be greater than zero")
    return MPG_TO_L100 / mpg


def l100km_to_mpg(l100):
    if l100 <= 0:
        raise ValueError("L/100km must be greater than zero")
    return MPG_TO_L100 / l100


def build_layout(on_back):
    """Return the converter widget tree. on_back is called by the Back button."""
    mpg_input = toga.TextInput(placeholder="mpg", style=Pack(flex=1))
    l100_input = toga.TextInput(placeholder="L/100km", style=Pack(flex=1))
    result = toga.Label("Enter a value in either field", style=Pack(padding_top=10))

    # Guard so that setting one field from the other does not loop.
    updating = {"busy": False}

    def on_mpg_change(widget):
        if updating["busy"]:
            return
        updating["busy"] = True
        try:
            value = float(mpg_input.value)
            l100 = mpg_to_l100km(value)
            l100_input.value = f"{l100:.2f}"
            result.text = f"{value:g} mpg = {l100:.2f} L/100km"
        except ValueError:
            result.text = "Enter a positive number"
        finally:
            updating["busy"] = False

    def on_l100_change(widget):
        if updating["busy"]:
            return
        updating["busy"] = True
        try:
            value = float(l100_input.value)
            mpg = l100km_to_mpg(value)
            mpg_input.value = f"{mpg:.2f}"
            result.text = f"{value:g} L/100km = {mpg:.2f} mpg"
        except ValueError:
            result.text = "Enter a positive number"
        finally:
            updating["busy"] = False

    mpg_input.on_change = on_mpg_change
    l100_input.on_change = on_l100_change

    title = toga.Label(
        "Fuel economy converter", style=Pack(font_weight="bold", padding_bottom=10)
    )
    row_mpg = toga.Box(
        children=[toga.Label("mpg", style=Pack(width=80)), mpg_input],
        style=Pack(direction="row", padding=5),
    )
    row_l100 = toga.Box(
        children=[toga.Label("L/100km", style=Pack(width=80)), l100_input],
        style=Pack(direction="row", padding=5),
    )
    back = toga.Button("Back", on_press=lambda w: on_back(), style=Pack(padding_top=20))

    return toga.Box(
        children=[title, row_mpg, row_l100, result, back],
        style=Pack(direction="column", padding=20, flex=1),
    )


def startup_into(app, ev):
    """Runs on the app's loop: push the converter onto the main window."""
    window = app.main_window
    if window.content:
        if not hasattr(window, "content_stack"):
            window.content_stack = []
        window.content_stack.append((window.title, window.content))
    window.title = "MPG Converter"

    def on_back():
        # Restore the launcher view, then release the script's wait so the
        # launcher knows this script has finished.
        type(app).unstack_from(app)
        ev.set()

    window.content = build_layout(on_back=on_back)
    if not window.visible:
        window.show()


def standalone_startup(app):
    """Used when there is no host app: this script owns the whole Toga app."""
    app.main_window = toga.MainWindow(title="MPG Converter")
    app.main_window.content = build_layout(on_back=lambda: app.exit())
    app.main_window.show()


def main():
    app = toga.App.app
    if app:
        # Running inside MyPyStub: stack onto its loop, then hold this script
        # open until Back restores the previous view.
        ev = threading.Event()
        if app.loop:
            app.loop.call_soon(lambda: startup_into(app, ev))
        else:
            startup_into(app, ev)
        ev.wait()
    else:
        # Running standalone (e.g. on the desktop): start our own Toga App.
        app = toga.App(
            "MPG Converter",
            "com.example.mpgconverter",
            startup=standalone_startup,  # pyright: ignore[reportArgumentType]
        )
        app.main_loop()


# Do NOT call main() at module level. MyPyStub's launcher loads this module
# and then calls main() itself, so a module-level call would run it twice.
# The desktop start-up runs only when the file is executed directly.
if __name__ == "__main__":
    main()
