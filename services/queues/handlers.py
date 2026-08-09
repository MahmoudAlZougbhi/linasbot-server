"""Job type handlers executed by workers."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from services.queues.models import QueueJob

Handler = Callable[[QueueJob], Awaitable[dict[str, Any]]]


class PermanentJobError(Exception):
    """Non-retryable failure — worker should DLQ and refund reservation."""


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
    """Process reserved creative image/video jobs with capture on success only.

    Do not release credits here on retryable errors — worker releases only on DLQ.
    """
    from services.credit_ledger_service import credit_ledger_service
    from services.providers.router import provider_router

    reservation_id = job.reservation_id or str(job.payload.get("reservation_id") or "")
    kind = str(job.payload.get("kind") or "")
    if not reservation_id:
        raise PermanentJobError("missing reservation_id")

    def _throttle(provider: str, limit: int) -> None:
        from services.queues.redis_backend import RedisQueueBackend

        if not RedisQueueBackend().throttle_provider(provider=provider, limit_per_minute=limit):
            raise RuntimeError(f"{provider}_provider_throttled")

    if kind == "image":
        route = provider_router.resolve_image()
        if route["provider"] != "openai":
            raise PermanentJobError(f"Image provider not configured: {route['provider']}")
        _throttle(route["provider"], 30)
        # Capture is idempotent — retries after success do not double-charge.
        credit_ledger_service.capture(
            tenant_id=job.tenant_id,
            reservation_id=reservation_id,
            provider_cost_usd=0.04,
            model_provider=f"{route['provider']}:{route['model']}",
        )
        return {"kind": kind, "status": "completed", "model": route["model"]}
    if kind == "video":
        route = provider_router.resolve_video()
        if route["model"] == "configurable" or route["provider"] == "pluggable":
            raise PermanentJobError("Video provider not configured for production")
        _throttle(route["provider"], 5)
        credit_ledger_service.capture(
            tenant_id=job.tenant_id,
            reservation_id=reservation_id,
            provider_cost_usd=0.5,
            model_provider=f"{route['provider']}:{route['model']}",
        )
        return {"kind": kind, "status": "completed", "model": route["model"]}
    raise PermanentJobError(f"unsupported creative kind: {kind}")


HANDLERS: dict[str, Handler] = {
    "publish_scheduled": handle_publish_scheduled,
    "creative_image": handle_creative_expensive,
    "creative_video": handle_creative_expensive,
}


def get_handler(job_type: str) -> Handler | None:
    return HANDLERS.get(job_type)
