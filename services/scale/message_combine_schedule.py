"""Enqueue or bump a delayed combine_flush job for one conversation."""

from __future__ import annotations

import time
from typing import Any


def schedule_combine_flush(
    *,
    user_key: str,
    tenant_id: str,
    conversation_key: str,
    due_at: float,
    payload: dict[str, Any] | None = None,
) -> str | None:
    """Return job id. Queued jobs are bumped; a processing job gets a follow-up."""
    from services.job_queue import job_queue
    from services.omnichannel.queues import physical_queue_for
    from services.queues.models import QueueJob

    backend = getattr(job_queue, "_redis", None)
    if backend is None:
        return None
    idem = f"combine_flush:{user_key}"
    existing = backend.get_by_idempotency("high_priority", tenant_id or "unknown", idem)
    if existing is not None and existing.status == "queued":
        backend.set_available_at(existing, due_at)
        return str(existing.id)
    if existing is not None and existing.status == "processing":
        generation = str((payload or {}).get("generation") or int(due_at * 1000))
        idem = f"combine_flush:{user_key}:g{generation}"
        existing = backend.get_by_idempotency("high_priority", tenant_id or "unknown", idem)
        if existing is not None and existing.status == "queued":
            backend.set_available_at(existing, due_at)
            return str(existing.id)
    if existing is not None and existing.status in {"completed", "dead"}:
        backend.clear_idempotency("high_priority", tenant_id or "unknown", idem)
    body = {
        **(payload or {}),
        "user_key": user_key,
        "_conversation_key": conversation_key,
        "_provider": "openai",
        "_logical_queue": "dm_urgent",
        "_priority": "customer_conversation",
    }
    job = QueueJob.new(
        queue=physical_queue_for("dm_urgent"),  # type: ignore[arg-type]
        job_type="combine_flush",
        tenant_id=tenant_id or "unknown",
        payload=body,
        idempotency_key=idem,
        available_at=due_at,
    )
    stored = backend.enqueue(job)
    return str(stored.id)


def seconds_until_due(due_at: float, *, now: float | None = None) -> float:
    ts = time.time() if now is None else float(now)
    return max(0.05, float(due_at) - ts)
