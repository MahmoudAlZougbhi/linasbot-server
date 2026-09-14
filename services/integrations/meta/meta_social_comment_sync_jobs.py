"""Queue handlers for Meta social comment sync."""

from __future__ import annotations

from typing import Any

from services.queues.models import QueueJob


async def handle_meta_social_comment_sync(job: QueueJob) -> dict[str, Any]:
    """Leftover Graph-poll jobs must not run. Inbound comments are webhook-only."""
    return {"skipped": True, "reason": "webhook_only", "job_id": job.id}
