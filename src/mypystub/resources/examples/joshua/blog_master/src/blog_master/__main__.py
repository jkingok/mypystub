from .app import main

if __name__ == "__main__":
    app = main()
    if app is not None:  # standalone: start the app's own loop
        app.main_loop()
