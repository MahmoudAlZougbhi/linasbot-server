"""Run N concurrent claim loops for one physical queue. SIGTERM stops new claims.

N can change over time (in-node autoscale). Extra slots stop between jobs.
"""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable, Coroutine
from typing import Any, cast

from services.queues.config import DEFAULT_CONCURRENCY

JobWorker = Callable[[], Awaitable[None]]
SlotCount = Callable[[], int]


def concurrency_for(queue: str) -> int:
    return max(1, int(DEFAULT_CONCURRENCY.get(queue, 1)))


def _run_cycle(one_cycle: JobWorker) -> None:
    awaitable = one_cycle()
    if asyncio.iscoroutine(awaitable):
        asyncio.run(cast(Coroutine[Any, Any, None], awaitable))


async def run_bounded_pool(
    *,
    queue: str,
    one_cycle: JobWorker,
    stopping: Callable[[], bool],
    slot_count: SlotCount | None = None,
) -> None:
    def target() -> int:
        if slot_count is None:
            return concurrency_for(queue)
        return max(1, int(slot_count()))

    executor = concurrent.futures.ThreadPoolExecutor(max_workers=24)
    live: dict[int, asyncio.Task[Any]] = {}
    next_id = 0

    async def slot(slot_id: int) -> None:
        loop = asyncio.get_running_loop()
        while not stopping() and slot_id < target():
            try:
                await loop.run_in_executor(executor, _run_cycle, one_cycle)
            except Exception:
                await asyncio.sleep(0.5)
            await asyncio.sleep(0)

    try:
        while True:
            want = 0 if stopping() else target()
            while len(live) < want:
                slot_id = next_id
                next_id += 1
                live[slot_id] = asyncio.create_task(slot(slot_id), name=f"{queue}-slot-{slot_id}")
            for slot_id, task in list(live.items()):
                if task.done():
                    live.pop(slot_id, None)
            if stopping():
                if live:
                    await asyncio.gather(*live.values(), return_exceptions=True)
                    live.clear()
                break
            await asyncio.sleep(0.05)
    finally:
        executor.shutdown(wait=False)
