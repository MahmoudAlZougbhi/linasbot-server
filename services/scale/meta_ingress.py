"""Meta webhook ingress: durable persist → queue → ACK-safe dispatch.

Valkey is never the only authoritative copy of an accepted inbound event.
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict
from typing import Any

from services.meta_comment_events import ResolvedMetaCommentEvent
from services.meta_messaging import MetaMessagingSettings
from services.meta_multi_app_router import ResolvedMetaEvent
from services.queues.config import redis_required
from services.scale.inbound_event_store import (
    InboundEventRecord,
    get_inbound_event,
    mark_inbound_state,
    put_inbound_event,
    stable_event_id,
)

_runtime_logger = logging.getLogger("uvicorn.error")


def _settings_snapshot(settings: MetaMessagingSettings) -> dict[str, Any]:
    return asdict(settings)


def _conversation_key_dm(event: dict[str, Any], tenant_id: str) -> str:
    channel = str(event.get("channel") or "unknown").strip().lower()
    sender = str(event.get("sender_id") or event.get("sender") or "").strip()
    return f"{tenant_id}:{channel}:{sender}"


def _try_enqueue(*, event_id: str, kind: str, tenant_id: str, conversation_key: str) -> str | None:
    try:
        from services.job_queue import job_queue

        if (
            getattr(job_queue, "backend", None) != "redis"
            or not getattr(job_queue, "production_ready", False)
            or not redis_required()
        ):
            return None
        job = job_queue.enqueue(
            queue="high_priority",
            job_type="meta_inbound_process",
            tenant_id=tenant_id or "unknown",
            payload={
                "event_id": event_id,
                "kind": kind,
                "_conversation_key": conversation_key,
                "_provider": "openai",
                "_priority": "customer_conversation",
            },
            idempotency_key=f"meta_inbound:{event_id}",
        )
        return str(job.id)
    except Exception as exc:
        _runtime_logger.warning(
            "[meta-ingress] enqueue_failed event_id=%s type=%s",
            event_id,
            type(exc).__name__,
        )
        return None


def persist_meta_dm_accepted(resolved: ResolvedMetaEvent, *, global_key: str) -> tuple[str, bool]:
    """Persist DM before ACK. Returns (event_id, queued_on_redis)."""
    tenant_id = str(getattr(resolved.settings, "tenant_id", "") or resolved.binding.tenant_id or "")
    event_id = stable_event_id("meta_dm", global_key)
    existing = get_inbound_event(event_id)
    if existing is not None and existing.state == "completed":
        return event_id, True
    now = time.time()
    record = InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id=tenant_id,
        claim_namespace="meta_social_dm_global",
        claim_key=global_key,
        state="accepted",
        created_at=existing.created_at if existing else now,
        updated_at=now,
        payload=dict(resolved.event),
        settings_snapshot=_settings_snapshot(resolved.settings),
        binding_snapshot={
            "binding_id": resolved.binding.binding_id,
            "tenant_id": resolved.binding.tenant_id,
            "channel": resolved.binding.channel,
            "asset_id": resolved.binding.asset_id,
            "app_key": resolved.binding.app_key,
            "auth_flow": getattr(resolved.binding, "auth_flow", ""),
        },
        conversation_key=_conversation_key_dm(resolved.event, tenant_id),
        attempts=existing.attempts if existing else 0,
    )
    put_inbound_event(record)
    job_id = _try_enqueue(
        event_id=event_id,
        kind="meta_dm",
        tenant_id=tenant_id,
        conversation_key=record.conversation_key,
    )
    if job_id:
        mark_inbound_state(event_id, state="queued", queue_job_id=job_id)
        return event_id, True
    return event_id, False


def persist_meta_comment_accepted(resolved: ResolvedMetaCommentEvent, *, global_key: str) -> tuple[str, bool]:
    """Persist comment before ACK. Returns (event_id, queued_on_redis)."""
    tenant_id = str(resolved.binding.tenant_id or "")
    event_id = stable_event_id("meta_comment", global_key)
    now = time.time()
    record = InboundEventRecord(
        event_id=event_id,
        kind="meta_comment",
        tenant_id=tenant_id,
        claim_namespace="meta_social_comment_global",
        claim_key=global_key,
        state="accepted",
        created_at=now,
        updated_at=now,
        payload=dict(resolved.event),
        settings_snapshot=_settings_snapshot(resolved.settings),
        binding_snapshot={
            "binding_id": resolved.binding.binding_id,
            "tenant_id": resolved.binding.tenant_id,
            "channel": resolved.binding.channel,
            "asset_id": resolved.binding.asset_id,
            "page_id": resolved.binding.page_id,
            "instagram_account_id": resolved.binding.instagram_account_id,
            "app_key": resolved.binding.app_key,
            "auth_flow": getattr(resolved.binding, "auth_flow", ""),
            "credential_id": resolved.binding.credential_id,
            "status": resolved.binding.status,
            "generation": resolved.binding.generation,
            "created_at": resolved.binding.created_at,
            "updated_at": resolved.binding.updated_at,
        },
        conversation_key=(f"{tenant_id}:comment:{resolved.binding.asset_id}:{resolved.event.get('comment_id')}"),
    )
    put_inbound_event(record)
    job_id = _try_enqueue(
        event_id=event_id,
        kind="meta_comment",
        tenant_id=tenant_id,
        conversation_key=record.conversation_key,
    )
    if job_id:
        mark_inbound_state(event_id, state="queued", queue_job_id=job_id)
        return event_id, True
    return event_id, False


def mark_dm_processing(event_id: str) -> None:
    mark_inbound_state(event_id, state="processing", bump_attempts=True)


def mark_dm_completed(event_id: str, *, outbound_status: str = "sent_or_suppressed") -> None:
    mark_inbound_state(
        event_id,
        state="completed",
        ai_output_persisted=True,
        outbound_status=outbound_status,
    )


def mark_dm_failed(event_id: str, error: str) -> None:
    mark_inbound_state(event_id, state="failed", last_error=error)
