import threading
import toga

done = threading.Event()


def do_work():
    raise ValueError("You still don't meet my values")


if toga.App.app:
    toga.App.app.loop.call_soon(do_work)
else:
    print("No app running?")

done.wait()
