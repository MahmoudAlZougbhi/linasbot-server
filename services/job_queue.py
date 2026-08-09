"""Job queue facade: Redis when configured; file/in-process only for non-production."""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Literal

from services.queues.config import (
    DEFAULT_JOB_TIMEOUT_SECONDS,
    DEFAULT_MAX_ATTEMPTS,
    QUEUE_NAMES,
    redis_required,
    redis_url,
)
from services.queues.models import QueueJob
from storage.persistent_storage import _DATA_ROOT

QueueName = Literal["high_priority", "interactive", "background", "expensive"]


class JobQueue:
    def __init__(self, root: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._root = root or (Path(_DATA_ROOT) / "job_queue")
        self._root.mkdir(parents=True, exist_ok=True)
        self._redis = None
        self.backend = "in_process"
        self.production_ready = False
        if redis_url():
            try:
                from services.queues.redis_backend import RedisQueueBackend

                self._redis = RedisQueueBackend()
                self.backend = "redis"
                self.production_ready = True
            except Exception as exc:
                if redis_required():
                    raise
                self._init_error = str(exc)
        elif redis_required():
            self._init_error = "REDIS_URL required in production"
        else:
            self._init_error = None

    def enqueue(
        self,
        *,
        queue: QueueName,
        job_type: str,
        tenant_id: str,
        payload: dict[str, Any],
        idempotency_key: str | None = None,
        reservation_id: str | None = None,
    ) -> QueueJob:
        if queue not in QUEUE_NAMES:
            raise ValueError(f"Unknown queue: {queue}")
        job = QueueJob.new(
            queue=queue,
            job_type=job_type,
            tenant_id=tenant_id,
            payload=payload,
            idempotency_key=idempotency_key,
            reservation_id=reservation_id,
            max_attempts=DEFAULT_MAX_ATTEMPTS,
            timeout_seconds=DEFAULT_JOB_TIMEOUT_SECONDS,
        )
        if self._redis is not None:
            return self._redis.enqueue(job)
        with self._lock:
            self._path(job.id).write_text(json.dumps(job.to_dict()), encoding="utf-8")
            # Also push id into a simple file list for workers in local mode.
            list_path = self._root / f"{queue}.list"
            with list_path.open("a", encoding="utf-8") as fh:
                fh.write(job.id + "\n")
        return job

    def _path(self, job_id: str) -> Path:
        return self._root / f"{job_id}.json"

    def get(self, job_id: str) -> QueueJob | None:
        if self._redis is not None:
            return self._redis.get(job_id)
        path = self._path(job_id)
        if not path.is_file():
            return None
        return QueueJob.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def mark(self, job_id: str, *, status: str, last_error: str | None = None) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job.status = status
        job.last_error = last_error
        job.attempts += 1
        job.updated_at = time.time()
        if self._redis is not None:
            self._redis._save(job)  # noqa: SLF001 — internal persist for facade mark
            return
        with self._lock:
            self._path(job_id).write_text(json.dumps(job.to_dict()), encoding="utf-8")

    def depth(self) -> dict[str, int]:
        if self._redis is not None:
            return self._redis.depth()
        out: dict[str, int] = {}
        for name in QUEUE_NAMES:
            list_path = self._root / f"{name}.list"
            count = 0
            if list_path.is_file():
                count = sum(1 for line in list_path.read_text(encoding="utf-8").splitlines() if line.strip())
            out[name] = count
            out[f"{name}_processing"] = 0
            out[f"{name}_dlq"] = 0
        return out

    def health(self) -> dict[str, Any]:
        if self._redis is not None:
            ok = self._redis.ping()
            return {
                "ok": ok,
                "backend": self.backend,
                "production_ready": self.production_ready,
                "depths": self.depth(),
                "heartbeats": self._redis.heartbeats(),
            }
        return {
            "ok": not redis_required(),
            "backend": self.backend,
            "production_ready": False,
            "depths": self.depth(),
            "error": self._init_error,
            "note": "In-process/file queue — not durable across API restarts",
        }


job_queue = JobQueue()
