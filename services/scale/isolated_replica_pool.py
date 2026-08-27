"""In-process worker replica pool with heartbeat and self-heal to desired count."""

from __future__ import annotations

import asyncio
import os
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from services.queues.models import QueueJob
from services.queues.redis_backend import RedisQueueBackend
from services.scale.replica_controller import mark_worker_draining, record_event, worker_is_draining
from services.scale.self_heal import decide_restart
from services.scale.worker_registry import heartbeat, mark_dead

Handler = Callable[[QueueJob], Awaitable[None]]


class IsolatedReplica:
    def __init__(
        self,
        backend: RedisQueueBackend,
        queue: str,
        handler: Handler,
        *,
        node_id: str = "node-a",
        restart_count: int = 0,
    ) -> None:
        self.backend = backend
        self.queue = queue
        self.handler = handler
        self.node_id = node_id
        self.worker_id = f"iso-{uuid.uuid4().hex[:8]}"
        self.started_at = time.time()
        self.ready_at: float | None = None
        self.first_job_at: float | None = None
        self.last_beat = time.time()
        self.stopping = False
        self.hung = False
        self.inflight = 0
        self.restart_count = restart_count
        self.last_exit = ""
        self.task: asyncio.Task[Any] | None = None
        self.current_job_id = ""

    def _beat(self, status: str) -> None:
        if self.hung:
            return
        self.last_beat = time.time()
        heartbeat(
            self.worker_id,
            status=status,
            node_id=self.node_id,
            pid=os.getpid(),
            inflight=self.inflight,
            started_at=self.started_at,
            restart_count=self.restart_count,
            last_exit=self.last_exit,
        )

    async def run(self) -> None:
        self.ready_at = time.time()
        self._beat("ready")
        try:
            while not self.stopping or self.inflight:
                draining = worker_is_draining(self.worker_id) or self.stopping
                self._beat("draining" if draining else ("busy" if self.inflight else "ready"))
                if draining:
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
                self.current_job_id = job.id
                if self.first_job_at is None:
                    self.first_job_at = time.time()
                self._beat("busy")
                try:
                    await self.handler(job)
                    self.backend.complete(job)
                except asyncio.CancelledError:
                    self.last_exit = "cancelled"
                    self.backend._r.delete(self.backend._k("lease", job.id))
                    self.backend.reclaim_expired_leases(self.queue)
                    raise
                except Exception as exc:
                    self.last_exit = type(exc).__name__
                    self.backend.fail(job, error=f"{type(exc).__name__}:{exc}", retry=True)
                finally:
                    self.current_job_id = ""
                    self.inflight = max(0, self.inflight - 1)
        finally:
            mark_dead(self.worker_id, last_exit=self.last_exit or "stopped")


class IsolatedReplicaPool:
    def __init__(
        self,
        backend: RedisQueueBackend,
        *,
        queue: str,
        handler: Handler,
        node_id: str = "node-a",
    ) -> None:
        self.backend = backend
        self.queue = queue
        self.handler = handler
        self.node_id = node_id
        self.replicas: list[IsolatedReplica] = []
        self.recent_starts: list[float] = []
        self.replaced = 0

    @property
    def live_count(self) -> int:
        return len([item for item in self.replicas if item.task is not None and not item.task.done()])

    def _sweep_dead(self) -> int:
        dead = 0
        for replica in self.replicas:
            if replica.task is None or not replica.task.done():
                continue
            replica.last_exit = replica.last_exit or "task_done"
            mark_dead(replica.worker_id, last_exit=replica.last_exit)
            replica.task = None
            dead += 1
        return dead

    async def scale_to(
        self,
        desired: int,
        *,
        event_base: dict[str, Any] | None = None,
        crash_heal: bool = False,
    ) -> dict[str, Any]:
        desired = max(0, int(desired))
        self._sweep_dead()
        timeline: dict[str, Any] = dict(event_base or {})
        timeline["reconcile_started_at"] = time.time()
        timeline["from_workers"] = self.live_count
        timeline["to_workers"] = desired
        while self.live_count < desired:
            if crash_heal:
                decision = decide_restart(
                    restart_count=self.replaced,
                    recent_starts=self.recent_starts,
                )
                if not decision.allowed:
                    timeline["restart_blocked"] = decision.reason
                    break
                if decision.delay_seconds:
                    await asyncio.sleep(min(0.05, decision.delay_seconds) if desired > self.live_count + 4 else 0)
            replica = IsolatedReplica(
                self.backend,
                self.queue,
                self.handler,
                node_id=self.node_id,
                restart_count=self.replaced,
            )
            process_started = time.time()
            self.recent_starts.append(process_started)
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
                    "node_id": self.node_id,
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
        return timeline

    async def heal_stale(self, *, stale_after: float | None = None) -> int:
        limit = float(stale_after) if stale_after is not None else float(os.getenv("LINAS_WORKER_STALE_SEC") or "20")
        now = time.time()
        killed = 0
        for replica in list(self.replicas):
            if replica.task is None or replica.task.done() or replica.stopping:
                continue
            if now - replica.last_beat <= limit:
                continue
            replica.last_exit = "heartbeat_stale"
            await self.crash(replica.worker_id)
            killed += 1
        return killed

    async def maintain(self, desired: int) -> dict[str, Any]:
        stale = await self.heal_stale()
        missing_before = desired - self.live_count
        dead = self._sweep_dead()
        if dead:
            self.replaced += dead
        result = await self.scale_to(desired, crash_heal=bool(dead or stale))
        result["dead_swept"] = dead
        result["stale_killed"] = stale
        result["replaced"] = self.replaced
        result["missing_before"] = missing_before
        return result

    async def crash(self, worker_id: str) -> None:
        replica = next(item for item in self.replicas if item.worker_id == worker_id)
        replica.last_exit = "injected_crash"
        if replica.task:
            replica.task.cancel()
            await asyncio.gather(replica.task, return_exceptions=True)
        mark_dead(worker_id, last_exit="injected_crash")

    async def close(self) -> None:
        await self.scale_to(0)
