# CLAUDE.md

Guidance for Claude working in this repository. Keep this file short and current.

## Project

MyPyStub is a Python Briefcase/Toga prototype app for iOS, with macOS, Linux, and Windows targets. It is a launcher that runs user-supplied Python prototypes on-device.

- Track the latest Python and Toga releases. The maintainer already tests on Python 3.15, and CI runs on 3.15. Do not pin old versions in instructions or config; bump them when new releases land.
- The iOS runtime has no `subprocess` and limited stdlib. Code under `src/` must work there unless it is guarded by platform checks.
- **Prototypes stay standalone.** Scripts and examples must run unchanged as standalone Briefcase apps, so give them no MyPyStub-specific Python API: they use standard Python, Toga, or Rubicon, never `import mypystub`. The launcher may have internal helpers for its own UI. The takeover protocol (`main_window.content_stack`) is the deliberate exception; it is plain Toga and works outside MyPyStub too.

## Rules

- **Never commit to `main`.** Work on a `feature/...` branch and leave merging to the user.
- **Push feature branches whenever it helps; never push to `main`.** That includes follow-up commits to a branch that already has a pull request. Don't force-push, and don't push to a branch someone else owns.
- **Do not change the version.** Only Fastlane does. At release time it stamps the calver and build number into `pyproject.toml` with `scripts/set_version.py` and commits it (with `uv.lock`) alongside the release notes, so `main` carries the last released version (see README, "Releasing to TestFlight"). The CalVer header in `CHANGELOG` is also set by the TestFlight script.
- **Do not edit generated or vendored output** (`build/`, `docs/`, `launcher.zip`).
- **`main` depends only on public repositories.** Paired projects have a private `<name>-internal` repository and a public `<name>` one (`togax-jkingok-internal` and `togax-jkingok`). A feature branch may depend on an in-development branch of an internal repository; before it merges, point it at the public repository and a released tag. The PR gate checks this for PRs into `main` (`scripts/check_public_deps.py`).
- **Keep `main` public-safe.** `mirror-main.yml` (or the Fastlane `mirror` lane) mirrors `main`, and the release tags on it, to the public repo, so do not commit secrets, signing material, or private notes.

## Layout

- `src/mypystub/` is the app package.
- `tests/` holds real tests only. It is included by Briefcase via `test_sources`.
- `examples/` is a symlink to `src/mypystub/resources/examples/`, which is bundled and shown in the app's Examples category. It holds sample prototypes and scratch scripts that are not tests. Add or edit examples there, not in `tests/`.
- `devtools.py` is the on-device build pipeline (see below).

## Toga on iOS

All Toga code and widgets must come from the subset supported on iOS. Do not use widgets that are unsupported there, such as Table and Tree. Check the Toga iOS backend before using any widget.

Import Objective-C classes from `toga_iOS.libs` (inside `sys.platform == "ios"` branches, since desktop and CI only install `toga-core`). In the app, only classes or frameworks that toga_iOS doesn't provide go in `src/mypystub/bridge.py`; never call rubicon's `ObjCClass` or `load_library` anywhere else (`tests/test_objc_usage.py` enforces this). Examples must not import `bridge.py`. They use `toga_iOS.libs` directly, and like `bridge.py` they may use `ObjCClass` for classes it doesn't provide, never for ones it does.

## Simulator and emulator testing

- **Switches:** the iOS Simulator tool's normal tap doesn't flip a `UISwitch`. Tap with `duration` 0.2.
- **Text:** pasting from the macOS clipboard into the Simulator doesn't work. Type with the tool's `text` action (Android: `adb shell input text`).
- **Coordinates:** taps are in device points. Work them out from the screenshot's fraction of the point size, not from the tap space the tool reports, which is wrong on some devices (the iPhone 13 mini reports 360×780 but is 375×812). Landscape screenshots may come back turned, so map the coordinates.
- **iOS 26.x simulators:** rotation is unreliable and can stay in landscape. Prefer iOS 27 devices for rotation tests.
- **Output:** launch with `xcrun simctl launch --console-pty <udid> <bundle id>` to see the app's stdout. On Android, stdout goes to `app_runtime.log` (the Logs tab), not logcat. Launch the app ID in `build/mypystub/android/gradle/app/build.gradle`; an older build with another ID may also be installed.
- **Builds:** move `build/mypystub` between worktrees and run `briefcase build iOS -u` (or `android -u -r`) instead of creating again. For Android, run `uv run scripts/pin_git_requirements.py` first, then restore `pyproject.toml` and `git checkout uv.lock`.
- **Layout:** check each tab the first time it's opened after a cold launch. Tabs not on screen at launch start at 0×0, notably on iPad. SafeArea's readings are in the Logs tab.

## Standards

Two tiers. Desktop and CI use industry-standard tools. The on-device pipeline is the exception and uses a limited set.

- **Desktop and CI (industry standard):** ruff for lint and format, pyright for types, pytest for tests. These run in `pr-gate.yml` and in pre-commit (`.pre-commit-config.yaml`). The same versions and configuration must run on desktop and in CI.
- **On device (embeddable only):** `devtools.py` uses Black, pyflakes, pycodestyle, and mypy, which are importable Python modules. Nothing on device may be a separate executable, because the App Store and TestFlight will reject the build.
- Type hints on all functions. Docstrings on public modules, classes, and functions.
- **Log, don't print.** Launcher and `togax_jkingok` code reports with `logging.getLogger(__name__)`, never `print()`: while a script runs, stdout is its output. `logfile.install` makes the log file logging's handler of last resort, so every record lands there unless a script configures logging itself (`tests/test_logfile_togax_logging.py` checks both).
- Line length 88.
- Tests: pytest. Add tests for logic before changing it.
- **Tests for a new, distinct feature go in a new file**, named `tests/test_<area>_<feature>.py` (for example `tests/test_ui_zipapps.py`; pytest only finds `test_*.py`), not appended to a busy file such as `tests/test_ui.py`. Tests added at the end of a shared file are where branches conflict. Edit an existing test file only to change the behaviour it already covers.
- **File length.** Aim to keep an example around 300 lines (the Info view folds source after 300, and the examples are read on a phone). Everywhere else, keep a file under 1,000 lines. As a file approaches its limit, try to separate it along logical lines. A single-file example is the exception: it stays whole, because one file is easy to share. A project-based example is not exempt, and splits like any other project. Tests follow the source: `ui_setup.py` pairs with `tests/test_ui_setup.py`.
- **Keep fixtures where they won't collect churn.** `tests/conftest.py` is for the few fixtures nearly every test needs (the dummy app and launcher). A fixture only one feature uses stays in that feature's test file. One shared by a few files goes in its own small module, `tests/support_<area>.py`, which they import. UI test files use the `app`, `docs` and `proto` fixtures from `conftest.py` and the helpers (`tap`, `run`, `wait_for`, `row`, …) from `tests/support_ui.py`.

## Commands

Use `uv` for everything except on-device code.

- `uv sync` installs the environment, including the `dev` group. `uv run pytest` runs tests.
- `uv run ruff check .`, `uv run ruff format --check .` and `uv run pyright` run the desktop checks (pyright is configured in `pyproject.toml`). Run `uv run ruff format .` before committing.
- `uv run pre-commit install` once per clone (and at the start of a cloud session) is required: it runs ruff, pyright, and pytest before each commit and each merge commit, which is what keeps CI minutes down. Never commit with `--no-verify`. `uv run pre-commit run --all-files` runs them by hand.
- `uv.lock` is committed. Run `uv lock` after changing dependencies.
- `python devtools.py` runs the on-device pipeline. It skips mypy on iOS.
- `briefcase run` launches the app. Simulator runs happen on the Mac, not in the cloud.

## Dependencies

Manage dependencies with `uv`. Prefer, in order: pure Python, binary wheels, then source-only distributions. Anything the on-device pipeline or the app imports must be embeddable: no separate executables, and no Rust or Node tooling in `devtools.py`. Desktop and CI tooling may be standard tools such as ruff, pyright, pytest, and pre-commit, but do not add to that set without asking.

## Commits and PRs

- A change a user would notice adds a fragment, `changes/<PR number>.feature.md` or `.bugfix.md` (see `changes/README.md`). Internal changes may add `.misc.md`, which isn't shown.
- Claude identifies itself in every commit message and PR.
- **PRs labelled `hold` are finished but deliberately not being merged.** Leave them alone unless asked about one specifically: don't review them further, push to them, or bring main into them; leave them out of merge-order planning and conflict checks; and don't include them in emulator, simulator or device test plans.
- Use the attribution lines your session provides, with the model and session URL of the **current** session. Do not copy them from older commits or this file. The shape is:
  - Commit messages end with `Co-Authored-By: Claude <model> <noreply@anthropic.com>` and `Claude-Session: <current session URL>`.
  - PR descriptions end with `🤖 Generated with [Claude Code](https://claude.com/claude-code)` and the current session URL.
