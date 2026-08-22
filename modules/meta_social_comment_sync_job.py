"""HA-safe Meta comment sync tick — polls Graph when feed/comments webhooks are absent."""

from __future__ import annotations

import time

from services.durable_event_claim import release_job_lock, try_acquire_job_lock
from services.job_queue import job_queue
from services.meta_app_registry import APP_A_KEY, get_meta_app_registry


async def run_meta_social_comment_sync_job() -> None:
    if not try_acquire_job_lock("meta_social_comment_sync_tick", ttl_seconds=55):
        return
    try:
        registry = get_meta_app_registry()
        bindings = [
            binding
            for binding in registry.list_bindings(include_inactive=False, include_superseded=False)
            if binding.app_key == APP_A_KEY
            and binding.status == "active"
            and binding.channel in {"facebook", "instagram"}
        ]
        bucket = int(time.time() // 60)
        for binding in bindings:
            job_queue.enqueue(
                queue="interactive",
                job_type="meta_social_comment_sync",
                tenant_id=binding.tenant_id,
                payload={"binding_id": binding.binding_id, "channel": binding.channel},
                idempotency_key=f"meta_comment_sync:{binding.binding_id}:{bucket}",
            )
    finally:
        release_job_lock("meta_social_comment_sync_tick")
