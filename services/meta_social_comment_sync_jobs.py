"""Queue handlers for Meta social comment sync."""

from __future__ import annotations

from typing import Any

from services.meta_app_registry import get_meta_app_registry
from services.meta_comment_permission_verification import (
    maybe_reconcile_binding_comment_permission,
    reconcile_binding_comment_permission,
)
from services.meta_social_comment_sync import _binding_by_id
from services.queues.models import QueueJob


async def handle_meta_social_comment_sync(job: QueueJob) -> dict[str, Any]:
    binding_id = str(job.payload.get("binding_id") or "").strip()
    channel = str(job.payload.get("channel") or "").strip().lower()
    if not binding_id:
        return {"skipped": True, "reason": "missing_binding_id"}

    registry = get_meta_app_registry()
    binding = _binding_by_id(registry, binding_id)
    if binding is not None and maybe_reconcile_binding_comment_permission(binding, registry=registry):
        binding = await reconcile_binding_comment_permission(binding, registry=registry)

    if channel == "facebook":
        from services.meta_social_comment_sync import sync_facebook_binding_comments

        return await sync_facebook_binding_comments(binding_id)
    if channel == "instagram":
        from services.meta_social_comment_sync import sync_instagram_binding_comments

        return await sync_instagram_binding_comments(binding_id)
    return {"skipped": True, "reason": "unsupported_channel"}
