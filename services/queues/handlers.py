"""Job type handlers executed by workers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.queues.models import QueueJob

Handler = Callable[[QueueJob], Awaitable[dict[str, Any]]]


class PermanentJobError(Exception):
    """Non-retryable failure — worker should DLQ and refund reservation."""


class JobNotReady(Exception):
    """Retry without consuming a hard attempt (conversation order wait)."""


async def handle_publish_scheduled(job: QueueJob) -> dict[str, Any]:
    from services.schedule_service import schedule_service

    post_id = str(job.payload.get("scheduled_post_id") or "")
    posts = schedule_service.list_for_tenant(job.tenant_id)
    post = next((p for p in posts if p.id == post_id), None)
    if post is None:
        raise PermanentJobError("scheduled post not found")
    if post.status == "canceled":
        return {"skipped": True, "reason": "canceled"}
    if post.status == "published":
        return {"skipped": True, "reason": "already_published"}
    from services.integration_capabilities import list_tenant_integration_status

    statuses = list_tenant_integration_status(job.tenant_id)
    live = False
    for row in statuses:
        if row.get("platform") not in {"facebook", "instagram", "meta"}:
            continue
        caps = row.get("capabilities") or {}
        publish = caps.get("content_publish") or {}
        if isinstance(publish, dict):
            live = bool(publish.get("live_verified"))
        else:
            live = publish == "connected"
        if live:
            break
    if not live:
        raise PermanentJobError("content_publish not live_verified for tenant")
    raise PermanentJobError("Meta publish provider path not live_verified — job not executed")


async def handle_creative_expensive(job: QueueJob) -> dict[str, Any]:
    """Creative Studio is cancelled. Drain leftover jobs to DLQ so the worker refunds."""
    raise PermanentJobError(f"creative_studio_cancelled:{job.job_type}")


async def handle_meta_inbound_process(job: QueueJob) -> dict[str, Any]:
    from services.queues.meta_inbound_handler import handle_meta_inbound_process as _impl

    return await _impl(job)


async def handle_tiktok_comment_sync(job: QueueJob) -> dict[str, Any]:
    from services.tiktok_business.jobs import handle_tiktok_comment_sync as _impl

    return await _impl(job)


async def handle_tiktok_comment_ai(job: QueueJob) -> dict[str, Any]:
    from services.tiktok_business.jobs import handle_tiktok_comment_ai as _impl

    return await _impl(job)


async def handle_meta_social_comment_sync(job: QueueJob) -> dict[str, Any]:
    from services.meta_social_comment_sync_jobs import handle_meta_social_comment_sync as _impl

    return await _impl(job)


async def handle_omni_generate(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.jobs import handle_omni_generate as _impl

    return await _impl(job)


async def handle_omni_deliver(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.jobs import handle_omni_deliver as _impl

    return await _impl(job)


async def handle_whatsapp_generate(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.jobs import handle_whatsapp_generate as _impl

    return await _impl(job)


async def handle_whatsapp_deliver_retry(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.jobs import handle_whatsapp_deliver_retry as _impl

    return await _impl(job)


async def handle_whatsapp_intent_deliver(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.jobs import handle_whatsapp_intent_deliver as _impl

    return await _impl(job)


async def handle_web_chat_generate(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.jobs import handle_web_chat_generate as _impl

    return await _impl(job)


async def handle_tiktok_webhook_event(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.jobs import handle_tiktok_webhook_event as _impl

    return await _impl(job)


async def handle_operator_deliver(job: QueueJob) -> dict[str, Any]:
    from services.omnichannel.jobs import handle_operator_deliver as _impl

    return await _impl(job)


async def handle_combine_flush(job: QueueJob) -> dict[str, Any]:
    from services.queues.combine_flush_handler import handle_combine_flush as _impl

    return await _impl(job)


async def handle_customer_ai_index(job: QueueJob) -> dict[str, Any]:
    from services.customer_ai.search.index_schedule import run_tenant_index_job

    revision = str(job.payload.get("revision") or "")
    reason = str(job.payload.get("reason") or "queued")
    result = await run_tenant_index_job(job.tenant_id, revision=revision, reason=reason)
    if result.get("ready"):
        return result
    if str(result.get("reason") or "") in {"unpublished", "tenant_required"}:
        raise PermanentJobError(str(result.get("reason") or "unpublished"))
    raise RuntimeError(str(result.get("reason") or "index_failed"))


HANDLERS: dict[str, Handler] = {
    "publish_scheduled": handle_publish_scheduled,
    "creative_image": handle_creative_expensive,
    "creative_video": handle_creative_expensive,
    "meta_inbound_process": handle_meta_inbound_process,
    "tiktok_comment_sync": handle_tiktok_comment_sync,
    "tiktok_comment_ai": handle_tiktok_comment_ai,
    "meta_social_comment_sync": handle_meta_social_comment_sync,
    "omni_generate": handle_omni_generate,
    "omnichannel_generate": handle_omni_generate,
    "omni_deliver": handle_omni_deliver,
    "omnichannel_deliver": handle_omni_deliver,
    "whatsapp_generate": handle_whatsapp_generate,
    "whatsapp_deliver_retry": handle_whatsapp_deliver_retry,
    "whatsapp_intent_deliver": handle_whatsapp_intent_deliver,
    "web_chat_generate": handle_web_chat_generate,
    "tiktok_webhook_event": handle_tiktok_webhook_event,
    "operator_deliver": handle_operator_deliver,
    "combine_flush": handle_combine_flush,
    "customer_ai_index": handle_customer_ai_index,
}


def get_handler(job_type: str) -> Handler | None:
    return HANDLERS.get(job_type)
