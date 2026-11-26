# App Template: notes for coding agents

This is a Toga app made from MyPyStub's project template. It runs inside the
MyPyStub launcher on iOS and Android, and on its own as a Briefcase app. Keep
both working. The full rules are in the skill,
`.claude/skills/mypystub-app/SKILL.md`; read it before changing anything.

## Yours to edit

- `src/app_template/app.py`: the app; `main()` is its entry point. Add modules
  beside it as it grows.
- `tests/`, `README.md`, `assets/src_icon.png`.
- `pyproject.toml`: only what its TODO comments point to (description,
  author, `requires-python`, `dependencies`, icon, iOS permissions).

## Not yours to edit

Shared with MyPyStub and replaced when the project is updated:
`src/app_template/bootstrap.py`, `__main__.py`, `hooks.py`, `script_tab.py`,
`run_status.py`, `logfile.py`, `android_back.py`, `android/java/`,
`generate_icons.py` and `.claude/skills/`.

## Commands

- `briefcase dev`: run it on this computer.
- `uv run pytest`: the tests. `uv run ruff check . && uv run ruff format .`
- `uv run generate_icons.py` once, then `briefcase build iOS` / `android`.
