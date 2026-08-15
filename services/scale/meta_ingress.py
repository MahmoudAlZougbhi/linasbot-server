"""Meta webhook ingress: durable persist → queue → ACK-safe dispatch.

Valkey is never the only authoritative copy of an accepted inbound event.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from services.meta_comment_events import ResolvedMetaCommentEvent
from services.meta_messaging import MetaMessagingSettings
from services.meta_multi_app_router import ResolvedMetaEvent
from services.queues.config import redis_required
from services.scale.inbound_event_store import (
    InboundEventRecord,
    create_inbound_event,
    get_inbound_event,
    mark_inbound_state,
    stable_event_id,
)

_runtime_logger = logging.getLogger("uvicorn.error")
_AMBIGUOUS_ENQUEUE = "__meta_enqueue_ack_unknown__"


def _settings_snapshot(settings: MetaMessagingSettings) -> dict[str, Any]:
    """Persist routing metadata only; credentials stay in the encrypted registry.

    Inbound records are copied to both the local durability ledger and Firestore.
    Storing the full dataclass here would therefore duplicate the Page/Instagram
    access token, App Secret, and webhook verify token as plaintext.  Workers
    resolve current credentials from the binding id at processing time instead.
    """

    return {
        "enabled": bool(settings.enabled),
        "page_id": settings.page_id,
        "instagram_account_id": settings.instagram_account_id,
        "graph_api_version": settings.graph_api_version,
        "app_id": settings.app_id,
        "app_key": settings.app_key,
        "tenant_id": settings.tenant_id,
        "binding_id": settings.binding_id,
        "auth_flow": settings.auth_flow,
        "graph_base_url": settings.graph_base_url,
    }


def _conversation_key_dm(event: dict[str, Any], tenant_id: str) -> str:
    channel = str(event.get("channel") or "unknown").strip().lower()
    sender = str(event.get("sender_id") or event.get("sender") or "").strip()
    return f"{tenant_id}:{channel}:{sender}"


def _try_enqueue(
    *,
    event_id: str,
    kind: str,
    tenant_id: str,
    conversation_key: str,
    claim_token: str = "",
    claim_generation: int = 1,
) -> str | None:
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
                "_claim_token": claim_token,
                "_claim_generation": claim_generation,
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
        return _AMBIGUOUS_ENQUEUE


def persist_meta_dm_accepted(resolved: ResolvedMetaEvent, *, global_key: str) -> tuple[str, bool]:
    """Persist DM before claim/ACK. Returns ``(event_id, created)``."""
    tenant_id = str(getattr(resolved.settings, "tenant_id", "") or resolved.binding.tenant_id or "")
    event_id = stable_event_id("meta_dm", global_key)
    now = time.time()
    record = InboundEventRecord(
        event_id=event_id,
        kind="meta_dm",
        tenant_id=tenant_id,
        claim_namespace="meta_social_dm_global",
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
            "app_key": resolved.binding.app_key,
            "auth_flow": getattr(resolved.binding, "auth_flow", ""),
        },
        conversation_key=_conversation_key_dm(resolved.event, tenant_id),
        attempts=0,
    )
    _, created = create_inbound_event(record, enforce_binding_deletion_fence=True)
    return event_id, created


def enqueue_meta_inbound_event(event_id: str, *, claim_handle: Any) -> str:
    """Return ``queued``, ``ambiguous``, or ``inline`` without double dispatch."""

    record = get_inbound_event(event_id)
    if record is None:
        return "ambiguous"
    job_id = _try_enqueue(
        event_id=event_id,
        kind=record.kind,
        tenant_id=record.tenant_id,
        conversation_key=record.conversation_key,
        claim_token=str(claim_handle.owner_token),
        claim_generation=int(claim_handle.generation),
    )
    if job_id and job_id != _AMBIGUOUS_ENQUEUE:
        mark_inbound_state(event_id, state="queued", queue_job_id=job_id)
        return "queued"
    if job_id == _AMBIGUOUS_ENQUEUE:
        # The queue may have accepted the deterministic job before its ACK was
        # lost. Never start an inline copy with the same claim capability.
        try:
            mark_inbound_state(event_id, state="queued", last_error="enqueue_ack_unknown")
        except Exception:
            pass
        return "ambiguous"
    return "inline"


def persist_meta_comment_accepted(resolved: ResolvedMetaCommentEvent, *, global_key: str) -> tuple[str, bool]:
    """Persist comment before claim/ACK. Returns ``(event_id, created)``."""
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
        attempts=0,
    )
    _, created = create_inbound_event(record, enforce_binding_deletion_fence=True)
    return event_id, created


def mark_dm_processing(event_id: str) -> None:
    mark_inbound_state(event_id, state="processing", bump_attempts=True)


def mark_dm_completed(
    event_id: str,
    *,
    outbound_status: str = "sent_or_suppressed",
    ai_output_persisted: bool = True,
) -> None:
    mark_inbound_state(
        event_id,
        state="completed",
        ai_output_persisted=ai_output_persisted,
        outbound_status=outbound_status,
    )


def mark_dm_failed(event_id: str, error: str) -> None:
    mark_inbound_state(event_id, state="failed", last_error=error)
