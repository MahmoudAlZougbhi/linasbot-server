"""Worker process loop for one queue name with real bounded concurrency."""

from __future__ import annotations

import asyncio
import os
import signal
import uuid
from typing import Any

from services.omnichannel.worker_pool import run_bounded_pool
from services.queues.config import DEFAULT_TENANT_INFLIGHT, redis_url
from services.queues.handlers import PermanentJobError, get_handler
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

    async def _process_one(self) -> None:
        if self._stopping or not shutdown_coordinator.accept_queue_work:
            await asyncio.sleep(0.05)
            return
        try:
            self._backend.heartbeat(worker_id=self.worker_id, queue=self.queue)
            job = self._backend.claim(self.queue, worker_id=self.worker_id, timeout=3)
        except Exception:
            await asyncio.sleep(0.5)
            return
        if job is None:
            return
        if not shutdown_coordinator.track_job_enter():
            self._backend.requeue_soft(job, delay_seconds=0.2)
            return
        conv_lease = None
        held_inflight = False
        try:
            try:
                busy = self._backend.tenant_inflight(job.tenant_id) >= DEFAULT_TENANT_INFLIGHT
            except Exception:
                try:
                    self._backend.requeue_soft(job, delay_seconds=0.5)
                except Exception:
                    pass
                await asyncio.sleep(0.5)
                return
            if busy:
                self._backend.requeue_soft(job, delay_seconds=1.0)
                return
            delay = self._provider_gate(job)
            if delay is not None:
                self._backend.requeue_soft(job, delay_seconds=delay)
                return
            held_inflight = True
            conv_key = self._conversation_key(job)
            if conv_key:
                from services.scale.conversation_lock import ConversationLock

                conv_lease = ConversationLock().try_acquire(conv_key, ttl_seconds=max(30, int(job.timeout_seconds)))
                if conv_lease is None:
                    self._backend.requeue_soft(job, delay_seconds=0.5)
                    return
            self._backend.incr_tenant_inflight(job.tenant_id)
            try:
                handler = get_handler(job.job_type)
                if handler is None:
                    self._backend.fail(job, error=f"unknown_job_type:{job.job_type}", retry=False)
                    self._refund_if_needed(job)
                    return
                await asyncio.wait_for(handler(job), timeout=job.timeout_seconds)
                self._backend.complete(job)
            except PermanentJobError as exc:
                self._backend.fail(job, error=f"PermanentJobError:{exc}", retry=False)
                self._refund_if_needed(job)
            except Exception as exc:
                went_dead = self._backend.fail(job, error=f"{type(exc).__name__}:{exc}", retry=True)
                if went_dead:
                    self._refund_if_needed(job)
            finally:
                self._backend.decr_tenant_inflight(job.tenant_id)
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
