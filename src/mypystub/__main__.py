from .app import main

if __name__ == "__main__":
    if (m := main()):
        m.main_loop()
