"""SafeArea logs what the platform reports and what it applies, once per change (#305)."""

import toga

from mypystub.safe_area import AndroidMeasure, Insets, SafeColumn


def test_readings_and_padding_are_logged_once_per_change(capsys) -> None:
    area = SafeColumn(children=[toga.MultilineTextInput(flex=1)])
    measure = AndroidMeasure(
        Insets(48, 0, 126, 0), 0, (0, 0, 1080, 2400), (1080.0, 2400.0)
    )
    area.android_changed(measure, 2.625)
    area.android_changed(measure, 2.625)  # the same again: not logged again
    area.set_insets(Insets(18, 0, 48, 0))
    area.set_insets(Insets(18, 0, 48, 0))  # unchanged: not logged again
    lines = capsys.readouterr().out.splitlines()
    readings = [line for line in lines if "reading:" in line]
    applied = [line for line in lines if "padding applied" in line]
    assert len(readings) == 1 and readings[0].startswith(
        "SafeArea[MultilineTextInput] Android reading:"
    )
    assert "density=2.6" in readings[0]
    assert applied == ["SafeArea[MultilineTextInput] padding applied: (18, 0, 48, 0)"]


def test_an_empty_box_is_named_too() -> None:
    assert SafeColumn().describe() == "SafeArea[empty]"
