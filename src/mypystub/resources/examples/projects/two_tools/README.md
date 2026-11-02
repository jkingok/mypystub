# Two Tools

One project with several entry points, declared in `pyproject.toml`:

- **greet** (console): greets `--name`, using `GREETING` if it's set.
- **shout** (console): prints its arguments in capitals. It's a classmethod, `two_tools.cli:Shout.run`.
- **window** (GUI): takes over the screen, then hands it back.
- **hello** and **settings** (the `two_tools.plugins` group): a plugin system's entry points. `settings` is a dictionary, so it can't be run.

Swipe right on **Two Tools** for **Setup** to set environment variables every entry point inherits. Swipe right on an entry point to set its own arguments and variables.
