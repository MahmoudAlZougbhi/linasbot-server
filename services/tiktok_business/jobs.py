"""Queue handlers for TikTok comment sync, AI replies, and token refresh."""

from __future__ import annotations

from typing import Any

from services.queues.models import QueueJob
from services.tiktok_business.comment_ai import process_tiktok_comment_ai
from services.tiktok_business.comment_sync import sync_connection_comments


async def handle_tiktok_comment_sync(job: QueueJob) -> dict[str, Any]:
    connection_id = str(job.payload.get("connection_id") or "")
    if not connection_id:
        return {"skipped": True, "reason": "missing_connection_id"}
    return await sync_connection_comments(
        tenant_id=job.tenant_id,
        connection_id=connection_id,
        owner=job.id,
    )


async def handle_tiktok_comment_ai(job: QueueJob) -> dict[str, Any]:
    return await process_tiktok_comment_ai(
        tenant_id=job.tenant_id,
        connection_id=str(job.payload.get("connection_id") or ""),
        comment_id=str(job.payload.get("comment_id") or ""),
        item_id=str(job.payload.get("item_id") or ""),
    )
