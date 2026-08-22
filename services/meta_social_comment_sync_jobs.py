"""Queue handlers for Meta social comment sync."""

from __future__ import annotations

from typing import Any

from services.queues.models import QueueJob


async def handle_meta_social_comment_sync(job: QueueJob) -> dict[str, Any]:
    binding_id = str(job.payload.get("binding_id") or "").strip()
    channel = str(job.payload.get("channel") or "").strip().lower()
    if not binding_id:
        return {"skipped": True, "reason": "missing_binding_id"}
    if channel == "facebook":
        from services.meta_social_comment_sync import sync_facebook_binding_comments

        return await sync_facebook_binding_comments(binding_id)
    if channel == "instagram":
        from services.meta_social_comment_sync import sync_instagram_binding_comments

        return await sync_instagram_binding_comments(binding_id)
    return {"skipped": True, "reason": "unsupported_channel"}
