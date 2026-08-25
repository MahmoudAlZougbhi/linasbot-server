"""Queue handlers for TikTok comment sync, AI replies, and token refresh."""

from __future__ import annotations

from typing import Any

from services.queues.models import QueueJob
from services.tiktok_business.comment_ai import process_tiktok_comment_ai


async def handle_tiktok_comment_sync(job: QueueJob) -> dict[str, Any]:
    """Leftover comment-poll jobs must not run. Inbound comments are webhook-only."""
    return {"skipped": True, "reason": "webhook_only", "job_id": job.id}


async def handle_tiktok_comment_ai(job: QueueJob) -> dict[str, Any]:
    return await process_tiktok_comment_ai(
        tenant_id=job.tenant_id,
        connection_id=str(job.payload.get("connection_id") or ""),
        comment_id=str(job.payload.get("comment_id") or ""),
        item_id=str(job.payload.get("item_id") or ""),
    )
