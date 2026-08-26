"""Run N concurrent claim loops for one physical queue. SIGTERM stops new claims."""

from __future__ import annotations

import asyncio
import concurrent.futures
from collections.abc import Awaitable, Callable

from services.queues.config import DEFAULT_CONCURRENCY

JobWorker = Callable[[], Awaitable[None]]


def concurrency_for(queue: str) -> int:
    return max(1, int(DEFAULT_CONCURRENCY.get(queue, 1)))


def _run_cycle(one_cycle: JobWorker) -> None:
    awaitable = one_cycle()
    if isinstance(awaitable, Awaitable):
        asyncio.run(awaitable)


async def run_bounded_pool(*, queue: str, one_cycle: JobWorker, stopping: Callable[[], bool]) -> None:
    n = concurrency_for(queue)
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=n + 2)
    tasks = [asyncio.create_task(_loop(one_cycle, stopping, executor), name=f"{queue}-slot-{i}") for i in range(n)]
    try:
        await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        executor.shutdown(wait=False)


async def _loop(
    one_cycle: JobWorker,
    stopping: Callable[[], bool],
    executor: concurrent.futures.ThreadPoolExecutor,
) -> None:
    loop = asyncio.get_running_loop()
    while not stopping():
        try:
            await loop.run_in_executor(executor, _run_cycle, one_cycle)
        except Exception:
            await asyncio.sleep(0.5)
        await asyncio.sleep(0)
