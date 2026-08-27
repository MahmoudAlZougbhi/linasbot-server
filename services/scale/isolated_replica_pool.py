"""In-process worker replica pool for isolated autoscale proof.

Starts/stops claim loops against a real Redis queue backend. Scale-down
marks draining, waits for the current job, then stops. Never kills mid-send
without letting reclaim/idempotency recover.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any, Callable, Awaitable

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.replica_controller import mark_worker_draining, record_event, worker_is_draining


Handler = Callable[[QueueJob], Awaitable[None]]


class IsolatedReplica:
    def __init__(self, backend: RedisQueueBackend, queue: str, handler: Handler) -> None:
        self.backend = backend
        self.queue = queue
        self.handler = handler
        self.worker_id = f"iso-{uuid.uuid4().hex[:8]}"
        self.started_at = time.time()
        self.ready_at: float | None = None
        self.first_job_at: float | None = None
        self.stopping = False
        self.inflight = 0
        self.task: asyncio.Task[Any] | None = None

    async def run(self) -> None:
        self.ready_at = time.time()
        while not self.stopping or self.inflight:
            if worker_is_draining(self.worker_id) or self.stopping:
                if self.inflight == 0:
                    break
                await asyncio.sleep(0.02)
                continue
            try:
                job = self.backend.try_claim(self.queue, worker_id=self.worker_id)
            except Exception:
                await asyncio.sleep(0.05)
                continue
            if job is None:
                if self.stopping or worker_is_draining(self.worker_id):
                    break
                await asyncio.sleep(0.01)
                continue
            self.inflight += 1
            if self.first_job_at is None:
                self.first_job_at = time.time()
            try:
                await self.handler(job)
                self.backend.complete(job)
            except Exception as exc:
                self.backend.fail(job, error=f"{type(exc).__name__}:{exc}", retry=True)
            finally:
                self.inflight = max(0, self.inflight - 1)


class IsolatedReplicaPool:
    def __init__(self, backend: RedisQueueBackend, *, queue: str, handler: Handler) -> None:
        self.backend = backend
        self.queue = queue
        self.handler = handler
        self.replicas: list[IsolatedReplica] = []

    @property
    def live_count(self) -> int:
        return len([item for item in self.replicas if item.task is not None and not item.task.done()])

    async def scale_to(self, desired: int, *, event_base: dict[str, Any] | None = None) -> dict[str, Any]:
        desired = max(0, int(desired))
        timeline: dict[str, Any] = dict(event_base or {})
        timeline["reconcile_started_at"] = time.time()
        timeline["from_workers"] = self.live_count
        timeline["to_workers"] = desired
        while self.live_count < desired:
            replica = IsolatedReplica(self.backend, self.queue, self.handler)
            process_started = time.time()
            replica.task = asyncio.create_task(replica.run(), name=replica.worker_id)
            self.replicas.append(replica)
            await asyncio.sleep(0)
            record_event(
                {
                    **timeline,
                    "worker_id": replica.worker_id,
                    "process_started_at": process_started,
                    "ready_at": replica.ready_at or time.time(),
                    "kind": "worker_boot",
                }
            )
        while self.live_count > desired:
            replica = next(item for item in reversed(self.replicas) if item.task and not item.task.done())
            mark_worker_draining(replica.worker_id, draining=True)
            replica.stopping = True
            drain_started = time.time()
            deadline = time.time() + 15
            while replica.inflight > 0 and time.time() < deadline:
                await asyncio.sleep(0.02)
            if replica.task:
                replica.task.cancel()
                await asyncio.gather(replica.task, return_exceptions=True)
            mark_worker_draining(replica.worker_id, draining=False)
            record_event(
                {
                    **timeline,
                    "worker_id": replica.worker_id,
                    "drain_started_at": drain_started,
                    "stopped_at": time.time(),
                    "kind": "worker_drain_stop",
                }
            )
        timeline["live_workers"] = self.live_count
        first_jobs = [item.first_job_at for item in self.replicas if item.first_job_at]
        if first_jobs:
            timeline["first_job_at"] = min(first_jobs)
        return timeline

    async def close(self) -> None:
        await self.scale_to(0)
