"""Make sure an error in a button or list handler is shown, not buried.

Toga catches every exception a handler raises, prints it to the log and carries
on, so the user sees nothing happen. :func:`guarded` wraps a handler so the
error also gets a dialog. The object the handler belongs to supplies the
dialog: a ``report_error(error, where)`` coroutine.

Kept free of Toga imports so it can be unit tested on desktop.
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import traceback
from collections.abc import Callable
from typing import Any


async def _report(owner: Any, error: Exception, where: str) -> None:
    """Show `error` with the owner's dialog; never raises itself."""
    try:
        await owner.report_error(error, where)
    except Exception:  # noqa: BLE001 - nothing more can be done, so log it
        traceback.print_exc()


def guarded[F: Callable[..., Any]](handler: F) -> F:
    """Wrap a method used as a handler so its errors are shown in a dialog.

    Works for plain and ``async`` methods. The error is still printed to the
    log. Cancellation is not an error and passes through.
    """
    where = handler.__name__.strip("_").replace("_", " ")
    if inspect.iscoroutinefunction(handler):

        @functools.wraps(handler)
        async def run_async(self: Any, *args: Any, **kwargs: Any) -> Any:
            try:
                return await handler(self, *args, **kwargs)
            except Exception as error:  # noqa: BLE001
                traceback.print_exc()
                await _report(self, error, where)

        run_async.__guarded__ = True  # type: ignore[attr-defined]
        return run_async  # type: ignore[return-value]

    @functools.wraps(handler)
    def run(self: Any, *args: Any, **kwargs: Any) -> Any:
        try:
            return handler(self, *args, **kwargs)
        except Exception as error:  # noqa: BLE001
            traceback.print_exc()
            asyncio.ensure_future(_report(self, error, where))

    run.__guarded__ = True  # type: ignore[attr-defined]
    return run  # type: ignore[return-value]
