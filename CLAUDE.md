# CLAUDE.md

Guidance for Claude working in this repository. Keep this file short and current.

## Project

MyPyStub is a Python Briefcase/Toga prototype app for iOS, with macOS, Linux, and Windows targets. It is a launcher that runs user-supplied Python prototypes on-device.

- Track the latest Python and Toga releases. The maintainer already tests on Python 3.15. Do not pin old versions in instructions or config. Pins in the repo (for example `toga-*~=0.5.0` and Python 3.14 in CI) are out of date and should be updated.
- The iOS runtime has no `subprocess` and limited stdlib. Code under `src/` must work there unless it is guarded by platform checks.

## Rules

- **Never commit to `main`.** Work on a `feature/...` branch and leave merging to the user.
- **Never push** without the user's explicit approval for that specific push.
- **Do not change the version.** `pyproject.toml` `version` and the CalVer header in `CHANGELOG` are set by the TestFlight script.
- **Do not edit generated or vendored output** (`build/`, `docs/`, `launcher.zip`).
- **Keep `main` public-safe.** `mirror-main.yml` mirrors `main` to the public repo, so do not commit secrets, signing material, or private notes.

## Layout

- `src/mypystub/` is the app package.
- `tests/` holds real tests only. It is included by Briefcase via `test_sources`.
- `examples/` holds sample prototypes and scratch scripts that are not tests. Planned: move the non-test files out of `tests/` into here.
- `devtools.py` is the on-device build pipeline (see below).

## Toga on iOS

All Toga code and widgets must come from the subset supported on iOS. Do not use widgets that are unsupported there, such as Table and Tree. Check the Toga iOS backend before using any widget.

## Standards

Two tiers. Desktop and CI use industry-standard tools. The on-device pipeline is the exception and uses a limited set.

- **Desktop and CI (industry standard):** ruff for lint and format, pyright for types, pytest for tests. These run in `pr-gate.yml` and, once added, in pre-commit. The same versions and configuration must run on desktop and in CI.
- **On device (embeddable only):** `devtools.py` uses Black, pyflakes, pycodestyle, and mypy, which are importable Python modules. Nothing on device may be a separate executable, because the App Store and TestFlight will reject the build.
- Type hints on all functions. Docstrings on public modules, classes, and functions.
- Line length 88.
- Tests: pytest. Add tests for logic before changing it.

## Commands

Use `uv` for everything except on-device code.

- `uv sync` installs the environment. `uv run pytest` runs tests.
- `uv run ruff check .` and `uv run pyright src/` run the desktop checks.
- `python devtools.py` runs the on-device pipeline. It skips mypy on iOS.
- `briefcase run` launches the app. Simulator runs happen on the Mac, not in the cloud.

## Dependencies

Manage dependencies with `uv`. Prefer, in order: pure Python, binary wheels, then source-only distributions. Anything the on-device pipeline or the app imports must be embeddable: no separate executables, and no Rust or Node tooling in `devtools.py`. Desktop and CI tooling may be standard tools such as ruff and pyright, but do not add to that set without asking.

## Commits and PRs

- Claude identifies itself in every commit message and PR, using the attribution lines below.
- End commit messages with:
  `Co-Authored-By: Claude Haiku 5.5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01JRRpxMs44gfoZnqq9Sq45n`
- End PR descriptions with:
  `🤖 Generated with [Claude Code](https://claude.com/claude-code)`
  `https://claude.ai/code/session_01JRRpxMs44gfoZnqq9Sq45n`
