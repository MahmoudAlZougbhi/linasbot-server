"""Run N concurrent claim loops for one physical queue. SIGTERM stops new claims."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from services.queues.config import DEFAULT_CONCURRENCY

JobWorker = Callable[[], Awaitable[None]]


def concurrency_for(queue: str) -> int:
    return max(1, int(DEFAULT_CONCURRENCY.get(queue, 1)))


async def run_bounded_pool(*, queue: str, one_cycle: JobWorker, stopping: Callable[[], bool]) -> None:
    n = concurrency_for(queue)
    tasks = [asyncio.create_task(_loop(one_cycle, stopping), name=f"{queue}-slot-{i}") for i in range(n)]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


async def _loop(one_cycle: JobWorker, stopping: Callable[[], bool]) -> None:
    while not stopping():
        await one_cycle()
        await asyncio.sleep(0)
