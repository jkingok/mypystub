"""Ask for a line or two of text without taking over the screen.

On iOS this is a native alert (``UIAlertController``) with text fields: a
small modal over what's already showing. Elsewhere the launcher falls back to
a pushed screen (see ``Prototype.ask_fields``), since Toga has no text-input
dialog.

:func:`ask_fields` is the awaitable the launcher uses and has no Toga or UIKit
in it, so it is tested on desktop with a stand-in for the alert.
:func:`ask_for_input` is the UIKit part and exists on iOS only.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any

NATIVE = sys.platform == "ios"

# UIAlertActionStyle: default, cancel, destructive
DEFAULT, CANCEL, DESTRUCTIVE = 0, 1, 2

# An action: (button title, callback(title, *texts)) with an optional UIAlertActionStyle
Action = tuple[Any, ...]


@dataclass(frozen=True)
class Field:
    """One text field in a prompt: its label (shown as a placeholder), and any text."""

    label: str
    value: str = ""


# Shows an alert: (title, message, actions, fields)
Present = Callable[[str, str, Sequence[Action], Sequence[Field]], None]


def alert_message(message: str, fields: Sequence[Field]) -> str:
    """The line under an alert's title.

    A field's label is only a placeholder, which disappears once there's text
    in it. So a prompt with no message of its own names its fields when any of
    them starts filled in, or it wouldn't say what it's asking for.
    """
    if message or not any(field.value for field in fields):
        return message
    return ", ".join(field.label for field in fields)


async def ask_fields(
    present: Present,
    title: str,
    message: str,
    fields: Sequence[Field],
    ok: str = "Done",
    cancel: str = "Cancel",
) -> list[str] | None:
    """Show a prompt with `fields` and wait: the texts typed, or None if cancelled.

    `present` shows the alert and arranges for the callbacks to run when a
    button is tapped, as :func:`present_alert` does on iOS.
    """
    answer: asyncio.Future[list[str] | None] = (
        asyncio.get_running_loop().create_future()
    )

    def finish(value: list[str] | None) -> None:
        if not answer.done():
            answer.set_result(value)

    present(
        title,
        alert_message(message, fields),
        [
            (cancel, lambda button, *texts: finish(None), CANCEL),
            (ok, lambda button, *texts: finish(list(texts))),
        ],
        fields,
    )
    return await answer


if sys.platform == "ios":
    from rubicon.objc import (  # pyright: ignore[reportMissingImports]
        Block,
        ObjCInstance,
        objc_id,
    )
    from toga_iOS.libs import (  # pyright: ignore[reportMissingImports]
        UIAlertAction,
        UIAlertController,
    )

    def ask_for_input(
        w: Any,
        title: str,
        message: str,
        actions: Sequence[Action] | None = None,
        texts: int = 0,
        values: Sequence[str] = (),
        placeholders: Sequence[str] = (),
    ) -> None:
        """Present a native alert with action buttons and text input fields.

        :param w: The Toga app, whose main window the alert is shown over.
        :param title: Alert title.
        :param message: Alert description.
        :param actions: ``(button title, callback)`` tuples, optionally with a
            third item, the ``UIAlertActionStyle`` (0 default, 1 cancel,
            2 destructive). A tapped button's callback is called with its
            title followed by the text of every field.
        :param texts: How many text fields to attach.
        :param values: Starting text for each field.
        :param placeholders: Placeholder (label) for each field.
        """
        actions = list(actions or [])
        alert = UIAlertController.alertControllerWithTitle(
            title, message=message, preferredStyle=1
        )

        def add_field(index: int) -> None:
            def configure(field_ptr: Any) -> None:
                field = ObjCInstance(field_ptr)
                if index < len(values):
                    field.text = values[index]
                if index < len(placeholders):
                    field.placeholder = placeholders[index]

            alert.addTextFieldWithConfigurationHandler_(Block(configure, None, objc_id))

        for i in range(texts):
            add_field(i)

        handlers = {
            action[0]: action[1] for action in actions if len(action) > 1 and action[1]
        }

        def on_done(action_ptr: Any) -> None:
            button = str(ObjCInstance(action_ptr).title)
            if button in handlers:
                outputs = [str(tf.text) for tf in alert.textFields]
                handlers[button](button, *outputs)

        for action in actions:
            style = action[2] if len(action) > 2 else DEFAULT
            alert.addAction(
                UIAlertAction.actionWithTitle(
                    action[0], style=style, handler=Block(on_done, None, objc_id)
                )
            )

        w.main_window._impl.native.rootViewController.presentViewController(
            alert, animated=True, completion=None
        )

    def present_alert(
        app: Any,
        title: str,
        message: str,
        actions: Sequence[Action],
        fields: Sequence[Field],
    ) -> None:
        """Show a prompt as a native alert: the iOS `present` for :func:`ask_fields`."""
        ask_for_input(
            app,
            title,
            message,
            actions,
            texts=len(fields),
            values=[f.value for f in fields],
            placeholders=[f.label for f in fields],
        )
