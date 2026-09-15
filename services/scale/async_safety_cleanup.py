"""Cancellation-safe waiting for independently scheduled safety cleanup."""

from __future__ import annotations

import asyncio
from typing import Any


async def await_safety_task(task: asyncio.Task[Any]) -> tuple[Any | None, bool, BaseException | None]:
    """Finish a child task and separately report caller cancellation and child failure."""

    cancelled = False
    while not task.done():
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            if not task.done():
                cancelled = True
        except BaseException:  # noqa: BLE001 - inspect the completed child below
            if not task.done():
                raise
    try:
        return task.result(), cancelled, None
    except BaseException as exc:  # noqa: BLE001 - the caller decides which failure wins
        return None, cancelled, exc
