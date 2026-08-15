"""Lease heartbeat while awaiting slow external work (e.g. AI provider)."""

from __future__ import annotations

import asyncio

from services.web_chat.operation import OperationRuntime, refresh_operation_lease
from services.web_chat.operation_fsm import OperationFsmError
from services.web_chat.operation_lease import LEASE_TTL_SECONDS

HEARTBEAT_INTERVAL_SECONDS = max(15, LEASE_TTL_SECONDS // 3)


class OperationLeaseHeartbeat:
    """Renew owner+generation lease until stopped or fence is lost."""

    def __init__(self, runtime: OperationRuntime) -> None:
        self._runtime = runtime
        self._task: asyncio.Task[None] | None = None
        self.lost_lease = False

    async def start(self) -> None:
        if self._task is not None:
            return
        self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        task = self._task
        self._task = None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    async def _run(self) -> None:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_SECONDS)
            try:
                refresh_operation_lease(self._runtime)
            except OperationFsmError as exc:
                if exc.code == "lease_fence_stale":
                    self.lost_lease = True
                    return
                raise
