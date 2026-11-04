"""Tests for the awaitable text prompt, without Toga or UIKit."""

import asyncio
from typing import Any

from mypystub.prompts import CANCEL, Field, alert_message, ask_fields


def ask_with(tap: str, *typed: str) -> tuple[list[str] | None, list[Any]]:
    """Ask for two fields with a stand-in alert; "tap" the named button."""
    shown: list[Any] = []

    def present(title: str, message: str, actions: Any, fields: Any) -> None:
        shown.append((title, message, [a[0] for a in actions], list(fields), actions))
        button = next(a for a in actions if a[0] == tap)
        asyncio.get_running_loop().call_soon(button[1], tap, *typed)

    async def go() -> list[str] | None:
        return await ask_fields(
            present, "Add variable", "Name it", [Field("Name"), Field("Value", "v")]
        )

    return asyncio.run(go()), shown


def test_done_returns_the_texts() -> None:
    """Done gives back what was typed, in field order."""
    result, shown = ask_with("Done", "A", "1")
    assert result == ["A", "1"]
    title, message, buttons, fields, _ = shown[0]
    assert (title, message) == ("Add variable", "Name it")
    assert buttons == ["Cancel", "Done"]
    assert fields == [Field("Name"), Field("Value", "v")]


def test_cancel_returns_none() -> None:
    """Cancel gives None, and is styled as a cancel button."""
    result, shown = ask_with("Cancel", "A", "1")
    assert result is None
    cancel = shown[0][4][0]
    assert cancel[2] == CANCEL


def test_a_second_tap_is_ignored() -> None:
    """Only the first button tapped counts."""

    def present(title: str, message: str, actions: Any, fields: Any) -> None:
        loop = asyncio.get_running_loop()
        loop.call_soon(actions[1][1], "Done", "first")
        loop.call_soon(actions[0][1], "Cancel")

    async def go() -> list[str] | None:
        return await ask_fields(present, "t", "", [Field("x")])

    assert asyncio.run(go()) == ["first"]


def test_a_filled_field_keeps_its_label_in_the_message() -> None:
    """A placeholder disappears once there's text, so the message names the field."""
    assert alert_message("", [Field("File name", "a.py")]) == "File name"
    assert alert_message("", [Field("Name", "A"), Field("Value")]) == "Name, Value"


def test_empty_fields_need_no_message_and_a_message_is_kept() -> None:
    """Placeholders are showing, or the prompt already says what it wants."""
    assert alert_message("", [Field("Argument")]) == ""
    assert alert_message("Name it", [Field("Name", "A")]) == "Name it"


def test_the_alert_is_given_the_message() -> None:
    """What's shown is the message worked out from the fields."""
    shown: list[str] = []

    def present(title: str, message: str, actions: Any, fields: Any) -> None:
        shown.append(message)
        asyncio.get_running_loop().call_soon(actions[1][1], "Done", "x")

    async def go() -> list[str] | None:
        return await ask_fields(present, "t", "", [Field("File name", "a.py")])

    asyncio.run(go())
    assert shown == ["File name"]
