"""Raise an error on the Toga main thread, to test error display."""

import threading

import toga

done = threading.Event()


def do_work():
    try:
        raise ValueError("You still don't meet my values")
    finally:
        # The error is still reported. Without this the script would wait for
        # ever, because nothing else sets `done`, and so would never end.
        done.set()


if toga.App.app:
    toga.App.app.loop.call_soon(do_work)
else:
    print("No app running?")

done.wait()
