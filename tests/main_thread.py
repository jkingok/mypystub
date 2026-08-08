import threading
import toga

done = threading.Event()


def do_work():
    print("Hello world!")
    done.set()


toga.App.app.loop.call_soon(do_work)

done.wait()
