"""Accept Meta webhook events: persist and enqueue before Firestore claim.

Firestore claim is only taken on this request when Redis is down and the
event must run inline. Queued work claims in the worker so Meta's HTTP ACK
is not blocked on a slow shared lease.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from services.meta_comment_events import ResolvedMetaCommentEvent
from services.meta_controlled_evidence import log_meta_controlled_evidence, meta_evidence_surface
from services.meta_cross_flow_dedup import (
    GLOBAL_COMMENT_CLAIM_NAMESPACE,
    GLOBAL_DM_CLAIM_NAMESPACE,
    global_comment_claim_key,
    global_dm_claim_key,
)
from services.meta_multi_app_router import ResolvedMetaEvent

_runtime_logger = logging.getLogger("uvicorn.error")

TrackTask = Callable[[asyncio.Task[None]], None]
ProcessDm = Callable[..., Awaitable[dict[str, Any]]]
ProcessComment = Callable[..., Awaitable[Any]]


@dataclass(frozen=True)
class MetaWebhookAcceptCounts:
    accepted: int = 0
    duplicates: int = 0


async def _claim_inline_handle(
    *,
    namespace: str,
    global_key: str,
    firestore_collection: str,
    event_id: str,
    binding_id: str,
) -> Any:
    from services.durable_event_claim import meta_claim_binding_digest, try_claim_event_handle

    return await try_claim_event_handle(
        namespace,
        global_key,
        ttl_seconds=300.0,
        firestore_collection=firestore_collection,
        firestore_claim_metadata={
            "binding_id_sha256": meta_claim_binding_digest(binding_id),
            "inbound_event_id": event_id,
        },
        meta_binding_id=binding_id,
    )


async def process_inline_meta_dm(
    resolved: ResolvedMetaEvent,
    *,
    event_id: str,
    global_key: str,
    claim_handle: Any,
    process_dm: ProcessDm,
    log_prefix: str = "[meta-social]",
) -> None:
    from services.durable_event_claim import complete_event_claim, release_event_claim, run_under_event_claim
    from services.scale.inbound_event_store import mark_inbound_state
    from services.scale.meta_ingress import mark_dm_completed, mark_dm_failed, mark_dm_processing
    from services.social_messaging_processor import meta_social_outcome_requires_retry

    event = resolved.event
    channel = str(event.get("channel") or resolved.binding.channel or "unknown").strip().lower()
    evidence_surface = meta_evidence_surface(kind="meta_dm", channel=channel)
    _runtime_logger.info(
        "%s event_processing_started channel=%s app_key=%s event_id=%s",
        log_prefix,
        channel,
        resolved.settings.app_key,
        event_id,
    )
    mark_dm_processing(event_id)
    try:
        outcome = await run_under_event_claim(
            claim_handle,
            ttl_seconds=300.0,
            operation=lambda: process_dm(
                event,
                resolved.settings,
                inbound_event_id=event_id,
                tenant_id=resolved.binding.tenant_id,
                binding_id=resolved.binding.binding_id,
            ),
        )
        delivery = str((outcome or {}).get("delivery") or "unknown")
        if not meta_social_outcome_requires_retry(outcome):
            mark_dm_completed(
                event_id,
                outbound_status=delivery,
                ai_output_persisted=bool((outcome or {}).get("logical_reply_id")),
            )
            await complete_event_claim(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_dm_global_claims",
                claim_handle=claim_handle,
            )
            if delivery == "delivered" and (outcome or {}).get("provider_message_id_present") is True:
                evidence_outcome = "provider_accepted"
            elif delivery == "duplicate_suppressed":
                evidence_outcome = "duplicate_suppressed"
            else:
                evidence_outcome = "failed"
            log_meta_controlled_evidence(
                _runtime_logger,
                event_id=event_id,
                surface=evidence_surface,
                outcome=evidence_outcome,
            )
        else:
            mark_inbound_state(
                event_id,
                state="failed",
                outbound_status=delivery,
                ai_output_persisted=bool((outcome or {}).get("logical_reply_id")),
                last_error=f"delivery:{delivery}",
            )
            await release_event_claim(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_dm_global_claims",
                claim_handle=claim_handle,
            )
            log_meta_controlled_evidence(
                _runtime_logger,
                event_id=event_id,
                surface=evidence_surface,
                outcome="retry",
            )
        _runtime_logger.info(
            "%s event_processing_completed channel=%s app_key=%s event_id=%s",
            log_prefix,
            channel,
            resolved.settings.app_key,
            event_id,
        )
    except asyncio.CancelledError:
        log_meta_controlled_evidence(
            _runtime_logger,
            event_id=event_id,
            surface=evidence_surface,
            outcome="failed",
        )
        mark_dm_failed(event_id, "processing_cancelled")
        await release_event_claim(
            GLOBAL_DM_CLAIM_NAMESPACE,
            global_key,
            firestore_collection="meta_social_dm_global_claims",
            claim_handle=claim_handle,
        )
        raise
    except Exception as exc:
        log_meta_controlled_evidence(
            _runtime_logger,
            event_id=event_id,
            surface=evidence_surface,
            outcome="failed",
        )
        _runtime_logger.error(
            "%s event_processing_failed channel=%s type=%s event_id=%s",
            log_prefix,
            channel,
            type(exc).__name__,
            event_id,
        )
        mark_dm_failed(event_id, f"exception:{type(exc).__name__}")
        await release_event_claim(
            GLOBAL_DM_CLAIM_NAMESPACE,
            global_key,
            firestore_collection="meta_social_dm_global_claims",
            claim_handle=claim_handle,
        )
        raise


async def process_inline_meta_comment(
    resolved: ResolvedMetaCommentEvent,
    *,
    event_id: str,
    global_key: str,
    claim_handle: Any,
    process_comment: ProcessComment,
) -> None:
    from services.durable_event_claim import complete_event_claim, release_event_claim, run_under_event_claim
    from services.meta_comment_replies import comment_reply_requires_retry
    from services.scale.meta_ingress import mark_dm_completed, mark_dm_failed, mark_dm_processing

    evidence_surface = meta_evidence_surface(kind="meta_comment", channel=resolved.binding.channel)
    _runtime_logger.info(
        "[meta-comment] event_processing_started channel=%s tenant=%s auth_flow=%s event_id=%s",
        resolved.binding.channel,
        resolved.binding.tenant_id,
        resolved.binding.auth_flow,
        event_id,
    )
    mark_dm_processing(event_id)
    try:
        result = await run_under_event_claim(
            claim_handle,
            ttl_seconds=300.0,
            operation=lambda: process_comment(resolved, inbound_event_id=event_id),
        )
        if comment_reply_requires_retry(result):
            mark_dm_failed(event_id, f"comment:{result.status}:{result.reason}")
            await release_event_claim(
                GLOBAL_COMMENT_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_comment_global_claims",
                claim_handle=claim_handle,
            )
            _runtime_logger.warning(
                "[meta-comment] event_processing_retry channel=%s status=%s reason=%s auth_flow=%s",
                resolved.binding.channel,
                result.status,
                result.reason,
                resolved.binding.auth_flow,
            )
            log_meta_controlled_evidence(
                _runtime_logger,
                event_id=event_id,
                surface=evidence_surface,
                outcome="retry",
            )
            return
        mark_dm_completed(event_id, outbound_status=f"{result.status}:{result.reason}")
        await complete_event_claim(
            GLOBAL_COMMENT_CLAIM_NAMESPACE,
            global_key,
            firestore_collection="meta_social_comment_global_claims",
            claim_handle=claim_handle,
        )
        if result.status in {"sent", "sent_dm"}:
            evidence_outcome = "provider_accepted"
        elif result.status == "ignored" and result.reason == "already_replied":
            evidence_outcome = "duplicate_suppressed"
        else:
            evidence_outcome = "failed"
        log_meta_controlled_evidence(
            _runtime_logger,
            event_id=event_id,
            surface=evidence_surface,
            outcome=evidence_outcome,
        )
        _runtime_logger.info(
            "[meta-comment] event_processing_completed channel=%s status=%s reason=%s auth_flow=%s",
            resolved.binding.channel,
            result.status,
            result.reason,
            resolved.binding.auth_flow,
        )
    except asyncio.CancelledError:
        log_meta_controlled_evidence(
            _runtime_logger,
            event_id=event_id,
            surface=evidence_surface,
            outcome="failed",
        )
        mark_dm_failed(event_id, "processing_cancelled")
        await release_event_claim(
            GLOBAL_COMMENT_CLAIM_NAMESPACE,
            global_key,
            firestore_collection="meta_social_comment_global_claims",
            claim_handle=claim_handle,
        )
        raise
    except Exception as exc:
        log_meta_controlled_evidence(
            _runtime_logger,
            event_id=event_id,
            surface=evidence_surface,
            outcome="failed",
        )
        _runtime_logger.error(
            "[meta-comment] event_processing_failed channel=%s type=%s",
            resolved.binding.channel,
            type(exc).__name__,
        )
        mark_dm_failed(event_id, f"exception:{type(exc).__name__}")
        await release_event_claim(
            GLOBAL_COMMENT_CLAIM_NAMESPACE,
            global_key,
            firestore_collection="meta_social_comment_global_claims",
            claim_handle=claim_handle,
        )
        raise


async def accept_meta_dm_events(
    resolved_events: list[ResolvedMetaEvent],
    *,
    track_task: TrackTask,
    process_dm: ProcessDm,
    log_prefix: str = "[meta-social]",
    authenticated_outcome: str = "",
) -> MetaWebhookAcceptCounts:
    from services.scale.meta_ingress import enqueue_meta_inbound_event, persist_meta_dm_accepted

    accepted = 0
    duplicates = 0
    for resolved in resolved_events:
        event = resolved.event
        global_key = global_dm_claim_key(event)
        if global_key.endswith(":"):
            continue
        event_id, created = persist_meta_dm_accepted(resolved, global_key=global_key)
        dispatch = enqueue_meta_inbound_event(event_id, claim_handle=None)
        if authenticated_outcome:
            log_meta_controlled_evidence(
                _runtime_logger,
                event_id=event_id,
                surface=meta_evidence_surface(kind="meta_dm", channel=resolved.binding.channel),
                outcome=authenticated_outcome,
            )
        if dispatch == "inline":
            claim_handle = await _claim_inline_handle(
                namespace=GLOBAL_DM_CLAIM_NAMESPACE,
                global_key=global_key,
                firestore_collection="meta_social_dm_global_claims",
                event_id=event_id,
                binding_id=resolved.binding.binding_id,
            )
            if claim_handle is None:
                duplicates += 1
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=meta_evidence_surface(kind="meta_dm", channel=resolved.binding.channel),
                    outcome="duplicate_suppressed",
                )
                continue
            track_task(
                asyncio.create_task(
                    process_inline_meta_dm(
                        resolved,
                        event_id=event_id,
                        global_key=global_key,
                        claim_handle=claim_handle,
                        process_dm=process_dm,
                        log_prefix=log_prefix,
                    )
                )
            )
        if created:
            accepted += 1
        else:
            duplicates += 1
    return MetaWebhookAcceptCounts(accepted=accepted, duplicates=duplicates)


async def accept_meta_comment_events(
    resolved_comment_events: list[ResolvedMetaCommentEvent],
    *,
    track_task: TrackTask,
    process_comment: ProcessComment,
    authenticated_outcome: str = "",
) -> MetaWebhookAcceptCounts:
    from services.scale.meta_ingress import enqueue_meta_inbound_event, persist_meta_comment_accepted

    accepted = 0
    duplicates = 0
    for resolved_comment in resolved_comment_events:
        global_key = global_comment_claim_key(resolved_comment.event)
        if global_key.endswith(":"):
            continue
        event_id, created = persist_meta_comment_accepted(resolved_comment, global_key=global_key)
        dispatch = enqueue_meta_inbound_event(event_id, claim_handle=None)
        if authenticated_outcome:
            log_meta_controlled_evidence(
                _runtime_logger,
                event_id=event_id,
                surface=meta_evidence_surface(kind="meta_comment", channel=resolved_comment.binding.channel),
                outcome=authenticated_outcome,
            )
        if dispatch == "inline":
            claim_handle = await _claim_inline_handle(
                namespace=GLOBAL_COMMENT_CLAIM_NAMESPACE,
                global_key=global_key,
                firestore_collection="meta_social_comment_global_claims",
                event_id=event_id,
                binding_id=resolved_comment.binding.binding_id,
            )
            if claim_handle is None:
                duplicates += 1
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=meta_evidence_surface(
                        kind="meta_comment", channel=resolved_comment.binding.channel
                    ),
                    outcome="duplicate_suppressed",
                )
                continue
            track_task(
                asyncio.create_task(
                    process_inline_meta_comment(
                        resolved_comment,
                        event_id=event_id,
                        global_key=global_key,
                        claim_handle=claim_handle,
                        process_comment=process_comment,
                    )
                )
            )
        if created:
            accepted += 1
        else:
            duplicates += 1
    return MetaWebhookAcceptCounts(accepted=accepted, duplicates=duplicates)
