"""Worker process loop for one queue name."""

from __future__ import annotations

import asyncio
import os
import signal
import time
import uuid
from typing import Any

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

    def _provider_gate(self, job: Any) -> float | None:
        """Return soft delay seconds when provider/tenant backpressure says wait."""
        try:
            from services.scale.provider_limiter import ProviderLimiter

            limiter = ProviderLimiter()
            provider = str((job.payload or {}).get("_provider") or "openai").strip().lower()
            priority = str((job.payload or {}).get("_priority") or "customer_conversation")
            decision = limiter.check(provider=provider, tenant_id=job.tenant_id, priority=priority)
            if decision.allowed:
                return None
            return max(0.05, float(decision.retry_after_seconds))
        except Exception:
            return None

    async def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        while not self._stopping:
            if not shutdown_coordinator.accept_queue_work:
                break
            self._backend.heartbeat(worker_id=self.worker_id, queue=self.queue)
            job = self._backend.claim(self.queue, worker_id=self.worker_id, timeout=3)
            if job is None:
                continue
            if not shutdown_coordinator.track_job_enter():
                self._backend.requeue_soft(job, delay_seconds=0.2)
                break
            conv_lease = None
            try:
                if self._backend.tenant_inflight(job.tenant_id) >= DEFAULT_TENANT_INFLIGHT:
                    self._backend.requeue_soft(job, delay_seconds=1.0)
                    continue
                delay = self._provider_gate(job)
                if delay is not None:
                    self._backend.requeue_soft(job, delay_seconds=delay)
                    continue
                conv_key = self._conversation_key(job)
                if conv_key:
                    from services.scale.conversation_lock import ConversationLock

                    conv_lease = ConversationLock().try_acquire(conv_key, ttl_seconds=max(30, int(job.timeout_seconds)))
                    if conv_lease is None:
                        self._backend.requeue_soft(job, delay_seconds=0.5)
                        continue
                self._backend.incr_tenant_inflight(job.tenant_id)
                try:
                    handler = get_handler(job.job_type)
                    if handler is None:
                        self._backend.fail(job, error=f"unknown_job_type:{job.job_type}", retry=False)
                        self._refund_if_needed(job)
                        continue
                    await asyncio.wait_for(handler(job), timeout=job.timeout_seconds)
                    self._backend.complete(job)
                except PermanentJobError as exc:
                    self._backend.fail(job, error=f"PermanentJobError:{exc}", retry=False)
                    self._refund_if_needed(job)
                except Exception as exc:
                    went_dead = self._backend.fail(
                        job,
                        error=f"{type(exc).__name__}:{exc}",
                        retry=True,
                    )
                    if went_dead:
                        self._refund_if_needed(job)
                finally:
                    self._backend.decr_tenant_inflight(job.tenant_id)
            finally:
                if conv_lease is not None:
                    try:
                        from services.scale.conversation_lock import ConversationLock

                        ConversationLock().release(conv_lease)
                    except Exception:
                        pass
                shutdown_coordinator.track_job_exit()
            time.sleep(0.01)
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
