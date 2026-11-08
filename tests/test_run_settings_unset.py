"""Unsetting environment variables, and the system layer (#176). No Toga needed."""

from mypystub import run_settings as rs


def test_unset_names_round_trip_through_a_table() -> None:
    """Set values go under env, unset names under unset, sorted."""
    settings = rs.RunSettings(["a"], {"B": "2", "z": None, "A": None})
    table = settings.to_table()
    assert table == {"args": ["a"], "env": {"B": "2"}, "unset": ["A", "z"]}
    assert rs.RunSettings.from_table(table) == settings


def test_no_unset_key_when_nothing_is_unset() -> None:
    """The table stays as it was for existing files."""
    assert "unset" not in rs.RunSettings([], {"A": "1"}).to_table()


def test_bad_unset_names_and_types_are_ignored() -> None:
    """A hand-edited file can't make a bad name or a non-list matter."""
    table = {"env": {"A": "1"}, "unset": ["OK", "bad name", 3, "1ST"]}
    assert rs.RunSettings.from_table(table).env == {"A": "1", "OK": None}
    assert rs.RunSettings.from_table({"unset": "OK"}).env == {}


def test_a_name_both_set_and_unset_counts_as_unset() -> None:
    """The explicit one wins."""
    table = {"env": {"A": "1"}, "unset": ["A"]}
    assert rs.RunSettings.from_table(table).env == {"A": None}


def test_split_env() -> None:
    """Values and unset names are separated."""
    assert rs.split_env({"B": "2", "a": None, "C": None}) == ({"B": "2"}, ["a", "C"])


def test_an_inner_layer_can_unset_and_set_again() -> None:
    """Inner wins, None meaning unset."""
    merged = rs.merged_env([{"A": "1", "B": "2"}, {"A": None}, {"A": "3", "B": None}])
    assert merged == {"A": "3", "B": None}


def test_system_variables_show_with_a_marker_and_can_be_overridden() -> None:
    """The system layer's rows say where they came from until overridden."""
    system = rs.Layer(rs.SYSTEM, {"HOME": "/h", "TZ": "UTC"})
    rows = rs.effective_rows([system], {})
    assert [(r.name, r.value, r.source, r.inherited) for r in rows] == [
        ("HOME", "/h", "the system", True),
        ("TZ", "UTC", "the system", True),
    ]
    rows = rs.effective_rows([system], {"TZ": "Europe/London", "HOME": ""})
    home, tz = rows
    assert (home.value, home.inherited) == ("", False)  # blank override is a value
    assert (tz.value, tz.inherited) == ("Europe/London", False)


def test_deleting_an_override_brings_the_system_value_back() -> None:
    """With the override gone, the row is the system's again."""
    system = rs.Layer(rs.SYSTEM, {"TZ": "UTC"})
    own = {"TZ": "Europe/London"}
    del own["TZ"]
    (row,) = rs.effective_rows([system], own)
    assert row.value == "UTC" and row.inherited and not row.unset


def test_unset_rows_have_no_value_and_say_who_unset_them() -> None:
    """An unset variable is a distinct row, own or inherited."""
    system = rs.Layer(rs.SYSTEM, {"TZ": "UTC", "HOME": "/h"})
    setup = rs.Layer("Setup", {"TZ": None})
    rows = {r.name: r for r in rs.effective_rows([system, setup], {"HOME": None})}
    assert rows["TZ"].unset and rows["TZ"].source == "Setup" and rows["TZ"].value == ""
    assert rows["HOME"].unset and not rows["HOME"].inherited
