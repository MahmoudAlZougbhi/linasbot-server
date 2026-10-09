"""Queue worker used when queue_backend=pg. SIGTERM releases the open lease."""

from __future__ import annotations

import signal
import time
from collections.abc import Callable

from services.platform.pg_jobs import PG_QUEUES, PgDurableQueue
from services.queues.models import QueueJob

_OPEN: dict[str, QueueJob | None] = {"job": None}
_WORKER_ID = "pg-worker"


def release_open_lease(queue: PgDurableQueue, *, worker_id: str) -> None:
    job = _OPEN.get("job")
    if job is None:
        return
    queue.release_lease(job, worker_id=worker_id)
    _OPEN["job"] = None


def run_once(
    queue: PgDurableQueue,
    *,
    queue_name: str,
    worker_id: str,
    handler: Callable[[QueueJob], None],
) -> bool:
    if queue_name not in PG_QUEUES:
        raise ValueError(f"unknown queue {queue_name}")
    job = queue.claim(queue_name, worker_id=worker_id, timeout=30)
    if job is None:
        return False
    _OPEN["job"] = job
    try:
        handler(job)
    except Exception as exc:
        queue.fail(job, error=str(exc), retry=True)
        _OPEN["job"] = None
        return True
    queue.complete(job)
    _OPEN["job"] = None
    return True


_HANDLERS: dict[str, Callable[[QueueJob], None]] = {}


def register_handler(job_type: str, handler: Callable[[QueueJob], None]) -> None:
    _HANDLERS[job_type] = handler


def default_handler(job: QueueJob) -> None:
    handler = _HANDLERS.get(job.job_type)
    if handler is not None:
        handler(job)
        return
    if job.job_type == "scheduler_tick":
        return
    raise RuntimeError("handler_not_registered")


def serve(queue_name: str, *, worker_id: str = _WORKER_ID) -> None:
    queue = PgDurableQueue()
    install_stop_handler(queue, worker_id=worker_id)
    while True:
        worked = run_once(queue, queue_name=queue_name, worker_id=worker_id, handler=default_handler)
        if not worked:
            time.sleep(0.5)


def install_stop_handler(queue: PgDurableQueue, *, worker_id: str = _WORKER_ID) -> None:
    def _stop(_signum: int, _frame: object) -> None:
        release_open_lease(queue, worker_id=worker_id)
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, _stop)
    signal.signal(signal.SIGINT, _stop)
