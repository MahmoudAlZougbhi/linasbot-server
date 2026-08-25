"""HA-safe Meta comment sync tick — temporary Graph poll until Meta comment webhooks deliver."""

from __future__ import annotations

import os
import time

from services.durable_event_claim import release_job_lock, try_acquire_job_lock
from services.job_queue import job_queue
from services.meta_app_registry import APP_A_KEY, get_meta_app_registry

_DEFAULT_POLL_SECONDS = 15
_MAX_POLL_SECONDS = 300


def meta_comment_poll_enabled() -> bool:
    """Kill switch: set META_COMMENT_POLL_ENABLED=false when comment webhooks are live."""

    raw = str(os.getenv("META_COMMENT_POLL_ENABLED", "true") or "").strip().lower()
    if raw in {"0", "false", "no", "off"}:
        return False
    return meta_comment_poll_interval_seconds() > 0


def meta_comment_poll_interval_seconds() -> int:
    """Poll cadence while Meta does not deliver feed/comments webhooks (demo / pre-Advanced Access)."""

    raw = str(os.getenv("META_COMMENT_POLL_INTERVAL_SECONDS", str(_DEFAULT_POLL_SECONDS)) or "").strip()
    try:
        value = int(raw)
    except ValueError:
        value = _DEFAULT_POLL_SECONDS
    return max(0, min(value, _MAX_POLL_SECONDS))


def meta_comment_poll_lock_ttl_seconds() -> int:
    interval = meta_comment_poll_interval_seconds()
    if interval <= 0:
        return 5
    return max(5, interval - 3)


# Scheduler imports this at registration time (requires process restart to pick up env changes).
META_COMMENT_SYNC_POLL_SECONDS = meta_comment_poll_interval_seconds()


async def run_meta_social_comment_sync_job() -> None:
    if not meta_comment_poll_enabled():
        return
    interval = meta_comment_poll_interval_seconds()
    if interval <= 0:
        return
    if not try_acquire_job_lock(
        "meta_social_comment_sync_tick",
        ttl_seconds=meta_comment_poll_lock_ttl_seconds(),
    ):
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
        bucket = int(time.time() // interval)
        for binding in bindings:
            job_queue.enqueue(
                queue="high_priority",
                job_type="meta_social_comment_sync",
                tenant_id=binding.tenant_id,
                payload={"binding_id": binding.binding_id, "channel": binding.channel},
                idempotency_key=f"meta_comment_sync:{binding.binding_id}:{bucket}",
            )
    finally:
        release_job_lock("meta_social_comment_sync_tick")
