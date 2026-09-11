"""Enqueue or inline-run per-tenant Customer Brain indexing. No admin per tenant."""

from __future__ import annotations

import logging
from typing import Any

from services.cm.version_store import read_published_pointer

log = logging.getLogger("customer_ai.index_schedule")

JOB_TYPE = "customer_ai_index"
QUEUE_NAME = "expensive"


def uses_index_worker() -> bool:
    from services.omnichannel.enqueue import queue_is_durable, should_defer_to_worker

    return bool(queue_is_durable() and should_defer_to_worker())


def published_revision(tenant_id: str) -> str:
    pointer = read_published_pointer(tenant_id)
    if pointer is None:
        return ""
    return str(pointer.content_version_id or "").strip()


def enqueue_tenant_index(tenant_id: str, *, revision: str = "", reason: str = "publish") -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    if not tid:
        return {"ready": False, "reason": "tenant_required", "queued": False, "health": "FAILED"}
    rev = (revision or published_revision(tid)).strip()
    if not rev:
        return {"ready": False, "reason": "unpublished", "queued": False, "health": "NO_INDEX", "count": 0}
    from services.customer_ai.search.index_lifecycle import mark_building, mark_stale_durable
    from services.job_queue import job_queue

    mark_stale_durable(tid, revision=rev, reason=reason)
    mark_building(tid, revision=rev, reason=reason)
    job = job_queue.enqueue(
        queue=QUEUE_NAME,
        job_type=JOB_TYPE,
        tenant_id=tid,
        payload={"revision": rev, "reason": reason},
        idempotency_key=f"cai-index:{tid}:{rev}",
    )
    return {
        "ready": False,
        "indexing": True,
        "queued": True,
        "job_id": job.id,
        "version": rev,
        "reason": reason,
        "health": "BUILDING",
        "manual_index_required": False,
    }


async def schedule_tenant_index(
    tenant_id: str,
    *,
    revision: str = "",
    reason: str = "publish",
) -> dict[str, Any]:
    """Publish/edit path: worker when durable Redis is required, else inline Voyage build."""
    tid = (tenant_id or "").strip()
    if not tid:
        return {"ready": False, "reason": "tenant_required", "queued": False, "health": "FAILED"}
    rev = (revision or published_revision(tid)).strip()
    if not rev:
        return {"ready": False, "reason": "unpublished", "queued": False, "health": "NO_INDEX", "count": 0}
    if uses_index_worker():
        queued = enqueue_tenant_index(tid, revision=rev, reason=reason)
        return queued
    result = await run_tenant_index_job(tid, revision=rev, reason=reason)
    if result.get("ready"):
        return result
    from services.omnichannel.enqueue import queue_is_durable

    if queue_is_durable():
        queued = enqueue_tenant_index(tid, revision=rev, reason=f"retry:{reason}")
        return {**result, **queued, "ready": False, "health": "BUILDING"}
    return result


async def run_tenant_index_job(
    tenant_id: str,
    *,
    revision: str = "",
    reason: str = "queued",
    activate: bool = True,
) -> dict[str, Any]:
    tid = (tenant_id or "").strip()
    rev = (revision or published_revision(tid)).strip()
    if not tid:
        return {"ready": False, "reason": "tenant_required", "health": "FAILED", "count": 0}
    if not rev:
        return {"ready": False, "reason": "unpublished", "health": "NO_INDEX", "count": 0}
    from services.customer_ai.search.index_job import index_published_tenant
    from services.customer_ai.search.index_lifecycle import mark_building, mark_failed

    mark_building(tid, revision=rev, reason=reason)
    try:
        result = await index_published_tenant(tid, revision=rev, activate=activate)
    except Exception as exc:
        log.warning("tenant index job crashed tenant=%s err=%s", tid, type(exc).__name__)
        failed = mark_failed(tid, revision=rev, reason=f"job_error:{type(exc).__name__}")
        return {
            "ready": False,
            "reason": f"job_error:{type(exc).__name__}",
            "health": "FAILED",
            "retry_count": failed.get("retry_count"),
            "count": 0,
            "manual_index_required": False,
        }
    if not isinstance(result, dict):
        mark_failed(tid, revision=rev, reason="bad_result")
        return {"ready": False, "reason": "bad_result", "health": "FAILED", "count": 0}
    return {**result, "manual_index_required": False}
