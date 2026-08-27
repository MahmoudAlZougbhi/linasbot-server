"""Worker process loop for one queue name with real bounded concurrency."""

from __future__ import annotations

import asyncio
import os
import signal
import time
import uuid
from typing import Any

from services.omnichannel.worker_pool import run_bounded_pool
from services.queues.config import DEFAULT_TENANT_INFLIGHT, redis_url
from services.queues.handlers import JobNotReady, PermanentJobError, get_handler
from services.queues.redis_backend import RedisQueueBackend
from services.scale.shutdown import shutdown_coordinator


class WorkerRuntime:
    def __init__(self, queue: str) -> None:
        if not redis_url():
            raise RuntimeError("Worker requires REDIS_URL / LINAS_REDIS_URL")
        self.queue = queue
        self.worker_id = f"{queue}-{uuid.uuid4().hex[:8]}"
        self._backend = RedisQueueBackend()
        self._stopping = False
        self.started_at = time.time()
        self.node_id = (os.getenv("LINAS_NODE_ID") or "").strip()

    def _registry_beat(self, status: str, *, inflight: int = 0, last_exit: str = "") -> None:
        try:
            from services.scale.worker_registry import heartbeat as registry_beat

            registry_beat(
                self.worker_id,
                status=status,
                node_id=self.node_id,
                pid=os.getpid(),
                inflight=inflight,
                started_at=self.started_at,
                last_exit=last_exit,
            )
        except Exception:
            return

    def request_stop(self, *_args: Any) -> None:
        self._stopping = True
        shutdown_coordinator.begin_drain()

    def _refund_if_needed(self, job: Any) -> None:
        reservation_id = job.reservation_id or str((job.payload or {}).get("reservation_id") or "")
        if not reservation_id:
            return
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.release(tenant_id=job.tenant_id, reservation_id=reservation_id)

    def _conversation_key(self, job: Any) -> str | None:
        payload = job.payload or {}
        key = str(payload.get("_conversation_key") or "").strip()
        return key or None

    def _provider_name(self, job: Any) -> str:
        return str((job.payload or {}).get("_provider") or "openai").strip().lower() or "openai"

    def _provider_gate(self, job: Any) -> float | None:
        try:
            from services.omnichannel.limiter import DistributedProviderLimiter

            limiter = DistributedProviderLimiter()
            priority = str((job.payload or {}).get("_priority") or "customer_conversation")
            decision = limiter.try_enter(
                provider=self._provider_name(job),
                tenant_id=job.tenant_id,
                priority=priority,
            )
            if decision.allowed:
                return None
            return max(0.05, float(decision.retry_after_seconds))
        except Exception:
            return 5.0

    def _release_provider(self, job: Any) -> None:
        try:
            from services.omnichannel.limiter import DistributedProviderLimiter

            DistributedProviderLimiter().exit(provider=self._provider_name(job), tenant_id=job.tenant_id)
        except Exception:
            pass

    def _requeue(self, job: Any, delay_seconds: float) -> None:
        try:
            self._backend.requeue_soft(job, delay_seconds=delay_seconds)
        except Exception:
            pass

    def _fail(self, job: Any, *, error: str, retry: bool) -> bool:
        try:
            return bool(self._backend.fail(job, error=error, retry=retry))
        except Exception:
            return False

    async def _process_one(self) -> None:
        try:
            await self._process_one_inner()
        except Exception:
            await asyncio.sleep(0.5)

    async def _process_one_inner(self) -> None:
        if self._stopping or not shutdown_coordinator.accept_queue_work:
            await asyncio.sleep(0.05)
            return
        try:
            from services.scale.replica_controller import worker_is_draining

            if worker_is_draining(self.worker_id):
                await asyncio.sleep(0.05)
                return
        except Exception:
            pass
        try:
            self._backend.heartbeat(worker_id=self.worker_id, queue=self.queue)
            self._registry_beat("draining" if self._stopping else "ready")
            self._backend.reclaim_expired_leases(self.queue)
            job = self._backend.claim(self.queue, worker_id=self.worker_id, timeout=3)
        except Exception:
            await asyncio.sleep(0.5)
            return
        if job is None:
            return
        try:
            wait_ms = max(0.0, (time.time() - float(job.created_at)) * 1000.0)
            from services.scale.latency_histogram import observe

            observe("job_wait_ms", wait_ms)
            trace_id = str((job.payload or {}).get("trace_id") or (job.payload or {}).get("_trace_id") or "")
            if trace_id:
                from services.scale.trace_context import set_trace_id
                from services.scale.trace_span import mark

                set_trace_id(trace_id)
                mark(trace_id, "worker_started")
        except Exception:
            pass
        if not shutdown_coordinator.track_job_enter():
            self._requeue(job, 0.2)
            return
        conv_lease = None
        held_inflight = False
        counted_inflight = False
        try:
            try:
                busy = self._backend.tenant_inflight(job.tenant_id) >= DEFAULT_TENANT_INFLIGHT
            except Exception:
                self._requeue(job, 0.5)
                await asyncio.sleep(0.5)
                return
            if busy:
                self._requeue(job, 1.0)
                return
            delay = self._provider_gate(job)
            if delay is not None:
                self._requeue(job, delay)
                return
            held_inflight = True
            conv_key = self._conversation_key(job)
            if conv_key:
                from services.scale.worker_lock_policy import job_requires_conversation_lock

                if job_requires_conversation_lock(str(job.job_type or "")):
                    from services.scale.conversation_lock import ConversationLock

                    try:
                        conv_lease = ConversationLock().try_acquire(conv_key, ttl_seconds=max(30, int(job.timeout_seconds)))
                    except Exception:
                        self._requeue(job, 0.5)
                        await asyncio.sleep(0.5)
                        return
                    if conv_lease is None:
                        self._requeue(job, 0.5)
                        return
            try:
                self._backend.incr_tenant_inflight(job.tenant_id)
                counted_inflight = True
            except Exception:
                self._requeue(job, 0.5)
                await asyncio.sleep(0.5)
                return
            try:
                handler = get_handler(job.job_type)
                if handler is None:
                    self._fail(job, error=f"unknown_job_type:{job.job_type}", retry=False)
                    self._refund_if_needed(job)
                    return

                async def _refresh_lease() -> None:
                    while True:
                        await asyncio.sleep(8)
                        if not self._backend.refresh_lease(job.id, self.worker_id):
                            return

                refresh_task = asyncio.create_task(_refresh_lease())
                self._registry_beat("busy", inflight=1)
                try:
                    await asyncio.wait_for(handler(job), timeout=job.timeout_seconds)
                    try:
                        self._backend.complete(job)
                    except Exception:
                        await asyncio.sleep(0.5)
                finally:
                    refresh_task.cancel()
                    await asyncio.gather(refresh_task, return_exceptions=True)
            except JobNotReady:
                self._requeue(job, 0.2)
            except PermanentJobError as exc:
                self._fail(job, error=f"PermanentJobError:{exc}", retry=False)
                self._refund_if_needed(job)
            except Exception as exc:
                went_dead = self._fail(job, error=f"{type(exc).__name__}:{exc}", retry=True)
                if went_dead:
                    self._refund_if_needed(job)
            finally:
                if counted_inflight:
                    try:
                        self._backend.decr_tenant_inflight(job.tenant_id)
                    except Exception:
                        pass
        finally:
            if held_inflight:
                self._release_provider(job)
            if conv_lease is not None:
                try:
                    from services.scale.conversation_lock import ConversationLock

                    ConversationLock().release(conv_lease)
                except Exception:
                    pass
            shutdown_coordinator.track_job_exit()

    async def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        await run_bounded_pool(
            queue=self.queue,
            one_cycle=self._process_one,
            stopping=lambda: self._stopping or not shutdown_coordinator.accept_queue_work,
        )
        shutdown_coordinator.wait_for_idle(timeout_seconds=50)


def main() -> int:
    queue = (os.getenv("LINAS_WORKER_QUEUE") or "").strip()
    if queue not in {"high_priority", "interactive", "background", "expensive"}:
        raise SystemExit("Set LINAS_WORKER_QUEUE to a valid queue name")
    runtime = WorkerRuntime(queue)
    asyncio.run(runtime.run_forever())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
