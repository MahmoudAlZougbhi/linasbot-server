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

    def _refund_if_needed(self, job: Any) -> None:
        reservation_id = job.reservation_id or str((job.payload or {}).get("reservation_id") or "")
        if not reservation_id:
            return
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.release(tenant_id=job.tenant_id, reservation_id=reservation_id)

    async def run_forever(self) -> None:
        signal.signal(signal.SIGTERM, self.request_stop)
        signal.signal(signal.SIGINT, self.request_stop)
        while not self._stopping:
            self._backend.heartbeat(worker_id=self.worker_id, queue=self.queue)
            job = self._backend.claim(self.queue, worker_id=self.worker_id, timeout=3)
            if job is None:
                continue
            if self._backend.tenant_inflight(job.tenant_id) >= DEFAULT_TENANT_INFLIGHT:
                self._backend.requeue_soft(job, delay_seconds=1.0)
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
            time.sleep(0.01)


def main() -> int:
    queue = (os.getenv("LINAS_WORKER_QUEUE") or "").strip()
    if queue not in {"high_priority", "interactive", "background", "expensive"}:
        raise SystemExit("Set LINAS_WORKER_QUEUE to a valid queue name")
    runtime = WorkerRuntime(queue)
    asyncio.run(runtime.run_forever())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
