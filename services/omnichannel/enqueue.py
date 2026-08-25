"""Fail-closed accept: persist then enqueue. Never ACK after a silent drop."""

from __future__ import annotations

from typing import Any

from services.omnichannel.queues import physical_queue_for
from services.queues.config import redis_required

AMBIGUOUS_ENQUEUE = "__omni_enqueue_ack_unknown__"


def queue_is_durable() -> bool:
    from services.job_queue import job_queue

    return getattr(job_queue, "backend", None) == "redis" and bool(getattr(job_queue, "production_ready", False))


def should_defer_to_worker() -> bool:
    """Production durable path. Tests/dev without LINAS_REQUIRE_REDIS stay in-process."""
    return redis_required()


def enqueue_job(
    *,
    logical_queue: str,
    job_type: str,
    tenant_id: str,
    payload: dict[str, Any],
    idempotency_key: str,
    conversation_key: str = "",
    provider: str = "openai",
) -> str | None:
    from services.job_queue import job_queue

    if redis_required() and not queue_is_durable():
        raise RuntimeError("omnichannel_queue_unavailable")
    body = {
        **payload,
        "_conversation_key": conversation_key,
        "_provider": provider,
        "_logical_queue": logical_queue,
    }
    try:
        job = job_queue.enqueue(
            queue=physical_queue_for(logical_queue),  # type: ignore[arg-type]
            job_type=job_type,
            tenant_id=tenant_id or "unknown",
            payload=body,
            idempotency_key=idempotency_key,
        )
        return str(job.id)
    except Exception:
        if redis_required():
            return AMBIGUOUS_ENQUEUE
        raise
