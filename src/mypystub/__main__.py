"""
Main entry point for the app.
This is intended to work either (cascaded) from a compatible launcher or as the main entry point.
"""

from .app import main

if __name__ == "__main__":
    if m := main():
        m.main_loop()
