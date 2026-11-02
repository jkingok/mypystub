"""Tests for saved Setup settings and inherited environment variables."""

import os
from pathlib import PurePath

import pytest

from mypystub.run_settings import (
    EnvRow,
    Layer,
    RunSettings,
    can_move,
    effective_rows,
    env_name_problem,
    env_value_problem,
    merged_env,
    move,
    settings_key,
    sorted_env,
    usable_env,
)


def test_settings_round_trip_through_a_table() -> None:
    """Arguments keep their order; the environment is saved alphabetised."""
    settings = RunSettings(["b", "a"], {"b": "2", "A": "1"})
    table = settings.to_table()
    assert table == {"args": ["b", "a"], "env": {"A": "1", "b": "2"}}
    assert RunSettings.from_table(table) == settings


def test_environment_only_table() -> None:
    """Things without their own arguments save only the environment."""
    assert RunSettings(["x"], {"A": "1"}).to_table(with_args=False) == {
        "env": {"A": "1"}
    }


@pytest.mark.parametrize(
    "table",
    [None, {}, {"args": "not a list", "env": ["not", "a", "table"]}],
)
def test_missing_or_malformed_tables_are_empty(table: object) -> None:
    """Nothing saved, or something unreadable, means no settings."""
    assert RunSettings.from_table(table) == RunSettings()  # type: ignore[arg-type]


def test_values_are_read_as_text() -> None:
    """Hand-edited numbers in launcher.toml still come back as strings."""
    settings = RunSettings.from_table({"args": [1, 2.5], "env": {"N": 3}})
    assert settings == RunSettings(["1", "2.5"], {"N": "3"})


def test_settings_key_is_the_path_in_its_category() -> None:
    """Keys use the category and the path below it, with / separators."""
    assert settings_key("Examples", PurePath("basics/show_args.py")) == (
        "Examples/basics/show_args.py"
    )
    assert settings_key("Documents", PurePath("tools")) == "Documents/tools"
    assert settings_key("Documents", PurePath(".")) == "Documents"


def test_entry_points_add_their_name_to_the_package_key() -> None:
    """An entry point's settings sit under its package's path plus its name."""
    assert settings_key("Documents", PurePath("two_tools"), "greet") == (
        "Documents/two_tools:greet"
    )


def test_environment_is_alphabetised_ignoring_case() -> None:
    """Order doesn't matter for variables, so they're always shown A to Z."""
    env = {"beta": "1", "Alpha": "2", "ALPHA": "3", "gamma": "4"}
    assert [name for name, _ in sorted_env(env)] == ["ALPHA", "Alpha", "beta", "gamma"]


@pytest.mark.parametrize(
    "name", ["GREETING", "lower_case", "_private", "A1", "Mixed_Case_2"]
)
def test_portable_variable_names_are_allowed(name: str) -> None:
    """Letters, digits and underscores, not starting with a digit (POSIX)."""
    assert env_name_problem(name) is None


@pytest.mark.parametrize(
    ("name", "problem"),
    [
        ("", "Enter a name"),
        # setenv itself refuses these
        ("A=B", "letters, digits and _"),
        ("A\0B", "letters, digits and _"),
        # setenv accepts these, but shells and most tools can't use them
        ("MY VAR", "letters, digits and _"),
        (" GREETING", "letters, digits and _"),
        ("GREETING ", "letters, digits and _"),
        ("GREETING\n", "letters, digits and _"),
        ("A\tB", "letters, digits and _"),
        ("1ST", "can't start with a digit"),
        ("9", "can't start with a digit"),
        ("lower_case.and-dash", "letters, digits and _"),
        ("A-B", "letters, digits and _"),
        ("A$B", "letters, digits and _"),
        ("A;B", "letters, digits and _"),
        ("naïve", "letters, digits and _"),
        ("ＡＢ", "letters, digits and _"),  # fullwidth letters aren't ASCII
    ],
)
def test_unusable_variable_names_are_refused(name: str, problem: str) -> None:
    """Names a shell couldn't use are refused, with a reason."""
    result = env_name_problem(name)
    assert result is not None and problem in result


@pytest.mark.parametrize("value", ["", "spaces and = signs", "ünïcode ✓", "a\nb"])
def test_variable_values_can_be_any_text(value: str) -> None:
    """Values aren't limited, apart from NUL."""
    assert env_value_problem(value) is None


def test_variable_values_cant_contain_nul() -> None:
    """os.environ can't hold a NUL, so a value with one is refused."""
    result = env_value_problem("a\0b")
    assert result is not None and "NUL" in result


@pytest.mark.parametrize(
    ("name", "value"), [("", "1"), ("A=B", "1"), ("A\0B", "1"), ("A", "x\0y")]
)
def test_everything_setenv_refuses_is_refused_first(
    name: str, value: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """These would raise mid-run in os.environ, so the form refuses them first."""
    with pytest.raises((ValueError, OSError)):
        monkeypatch.setitem(os.environ, name, value)
    assert env_name_problem(name) is not None or env_value_problem(value) is not None


def test_unusable_variables_in_a_table_are_dropped() -> None:
    """A hand-edited launcher.toml can't break a run with a bad name or value."""
    table = {"env": {"OK": "1", "BAD NAME": "2", "A=B": "3", "1ST": "4", "NUL": "a\0b"}}
    assert RunSettings.from_table(table).env == {"OK": "1"}
    assert usable_env({"OK": 1, "": "x", "A-B": "y"}) == {"OK": "1"}


def test_inner_layers_override_outer_ones() -> None:
    """Setup, then the package, then the entry point: the innermost value wins."""
    setup = {"GREETING": "Hello", "DEBUG": "0"}
    package = {"GREETING": "Hi"}
    entry = {"DEBUG": "1", "NAME": "Ada"}
    assert merged_env([setup, package, entry]) == {
        "GREETING": "Hi",
        "DEBUG": "1",
        "NAME": "Ada",
    }


def test_effective_rows_show_where_inherited_values_come_from() -> None:
    """Each layer's form shows what's in effect there, marking inherited rows."""
    rows = effective_rows(
        [
            Layer("Setup", {"GREETING": "Hello", "DEBUG": "0"}),
            Layer("tools", {"B": "x"}),
        ],
        {"DEBUG": "1"},
    )
    assert rows == [
        EnvRow("B", "x", "tools"),
        EnvRow("DEBUG", "1"),
        EnvRow("GREETING", "Hello", "Setup"),
    ]
    assert [row.inherited for row in rows] == [True, False, True]


@pytest.mark.parametrize(
    ("index", "where", "result", "new_index"),
    [
        (2, "top", ["c", "a", "b", "d"], 0),
        (2, "up", ["a", "c", "b", "d"], 1),
        (1, "down", ["a", "c", "b", "d"], 2),
        (1, "bottom", ["a", "c", "d", "b"], 3),
        (0, "up", ["a", "b", "c", "d"], 0),
        (3, "bottom", ["a", "b", "c", "d"], 3),
    ],
)
def test_moving_arguments(
    index: int, where: str, result: list[str], new_index: int
) -> None:
    """Arguments move in place; moving past an end leaves them as they are."""
    items = ["a", "b", "c", "d"]
    assert move(items, index, where) == new_index  # type: ignore[arg-type]
    assert items == result


def test_which_moves_are_possible() -> None:
    """Top and Up need a row above; Down and Bottom need a row below."""
    assert not can_move(3, None, "up")
    assert not can_move(3, 0, "top") and not can_move(3, 0, "up")
    assert can_move(3, 0, "down") and can_move(3, 0, "bottom")
    assert can_move(3, 2, "up") and not can_move(3, 2, "bottom")
    assert not can_move(1, 0, "up") and not can_move(1, 0, "down")
