"""Wait for Meta social combine-delay tasks without cancelling a newer replacement."""

from __future__ import annotations

import asyncio
from typing import Any, cast

from handlers.text_handlers_firestore import _delayed_processing_tasks


async def await_delayed_processing(user_id: str) -> None:
    """Await the latest combine task without deleting a newer replacement."""

    while True:
        maybe_task = cast(asyncio.Task[Any] | None, _delayed_processing_tasks.get(user_id))
        if maybe_task is None:
            return
        task: asyncio.Task[Any] = maybe_task
        try:
            await asyncio.shield(task)
        except asyncio.CancelledError:
            current = asyncio.current_task()
            if current is not None and current.cancelling():
                raise
            replacement = _delayed_processing_tasks.get(user_id)
            if replacement is None or replacement is task:
                raise
            continue
        finally:
            if _delayed_processing_tasks.get(user_id) is task and task.done():
                _delayed_processing_tasks.pop(user_id, None)

        replacement = _delayed_processing_tasks.get(user_id)
        if replacement is None or replacement is task:
            return
