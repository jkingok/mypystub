"""Run the app: ``briefcase dev``, a built app, or MyPyStub."""

from app_template.bootstrap import main

if __name__ == "__main__":
    if started := main():
        started.main_loop()
