"""Durable queue protocol — Redis today, Kafka-capable tomorrow without rewriting handlers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from services.queues.models import QueueJob


@dataclass(frozen=True)
class QueueMetrics:
    depth_by_queue: dict[str, int]
    oldest_age_seconds: dict[str, float]
    dlq_by_queue: dict[str, int]


@runtime_checkable
class DurableQueue(Protocol):
    """Internal queue interface. Launch backend: Redis/Valkey. Future: Kafka/etc."""

    backend_name: str

    def enqueue(self, job: QueueJob) -> QueueJob: ...

    def claim(self, queue: str, *, worker_id: str, timeout: int = 5) -> QueueJob | None: ...

    def complete(self, job: QueueJob) -> None: ...

    def fail(self, job: QueueJob, *, error: str, retry: bool) -> bool: ...

    def requeue_soft(self, job: QueueJob, *, delay_seconds: float = 1.0) -> None: ...

    def depth(self) -> dict[str, int]: ...

    def metrics(self) -> QueueMetrics: ...

    def ping(self) -> bool: ...


def get_durable_queue() -> DurableQueue:
    """Return production queue adapter. Never returns an in-memory production fallback."""
    from services.queues.config import redis_required, redis_url
    from services.scale.redis_queue_adapter import RedisDurableQueue

    if not redis_url():
        if redis_required():
            raise RuntimeError("Durable queue required but REDIS_URL / LINAS_REDIS_URL unset")
        raise RuntimeError(
            "Durable queue unavailable: set REDIS_URL for shared workers. "
            "In-memory/file queues are not a production scale backend."
        )
    return RedisDurableQueue()


def try_get_durable_queue() -> DurableQueue | None:
    try:
        return get_durable_queue()
    except Exception:
        return None


def enqueue_normalized_event(
    *,
    queue: str,
    job_type: str,
    tenant_id: str,
    payload: dict[str, Any],
    idempotency_key: str | None = None,
    conversation_key: str | None = None,
) -> QueueJob:
    """Enqueue a normalized inbound/outbound event with optional conversation partition key."""
    from services.job_queue import job_queue

    body = dict(payload)
    if conversation_key:
        body["_conversation_key"] = conversation_key
    return job_queue.enqueue(
        queue=queue,  # type: ignore[arg-type]
        job_type=job_type,
        tenant_id=tenant_id,
        payload=body,
        idempotency_key=idempotency_key,
    )
