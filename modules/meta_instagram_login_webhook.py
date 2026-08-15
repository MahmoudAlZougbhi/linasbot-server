"""Public webhook endpoint for Instagram API with Instagram Login."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from modules.core import app
from services.meta_app_registry import APP_A_KEY, get_meta_app_configs, meta_multi_app_registry_enabled
from services.meta_comment_events import (
    ResolvedMetaCommentEvent,
    count_raw_comment_changes,
    resolve_registry_comment_events,
    summarize_comment_resolve_drops,
)
from services.meta_comment_replies import comment_reply_requires_retry, process_meta_comment_event
from services.meta_controlled_evidence import log_meta_controlled_evidence, meta_evidence_surface
from services.meta_cross_flow_dedup import (
    GLOBAL_COMMENT_CLAIM_NAMESPACE,
    GLOBAL_DM_CLAIM_NAMESPACE,
    global_comment_claim_key,
    global_dm_claim_key,
)
from services.meta_instagram_login_config import (
    instagram_login_config_status,
    verify_instagram_login_challenge_token,
    verify_instagram_login_webhook_signature,
)
from services.meta_messaging import InMemoryMessageDeduper, get_meta_messaging_settings
from services.meta_multi_app_router import ResolvedMetaEvent, resolve_registry_events
from services.social_messaging_processor import meta_social_outcome_requires_retry, process_meta_social_event

_message_deduper = InMemoryMessageDeduper(ttl_seconds=300.0)
_comment_deduper = InMemoryMessageDeduper(ttl_seconds=86400.0)
_background_tasks: set[asyncio.Task[None]] = set()
_runtime_logger = logging.getLogger("uvicorn.error")


def _track_task(task: asyncio.Task[None]) -> None:
    _background_tasks.add(task)

    def _done(completed: asyncio.Task[None]) -> None:
        _background_tasks.discard(completed)
        try:
            completed.result()
        except asyncio.CancelledError:
            _runtime_logger.warning("[instagram-login] background_processing_cancelled")
        except Exception as exc:
            _runtime_logger.error(
                "[instagram-login] background_processing_failed type=%s",
                type(exc).__name__,
            )

    task.add_done_callback(_done)


@app.get("/webhook/instagram-login")
async def verify_instagram_login_webhook(request: Request) -> Any:
    status = instagram_login_config_status()
    if not status.configured:
        raise HTTPException(status_code=503, detail="Instagram Login webhook verify token is not configured")
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and verify_instagram_login_challenge_token(token) and challenge is not None:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhook/instagram-login")
async def receive_instagram_login_webhook(request: Request) -> Any:
    settings = get_meta_messaging_settings()
    raw_body = await request.body()
    if not meta_multi_app_registry_enabled():
        raise HTTPException(status_code=503, detail="Meta registry is not enabled")
    if not instagram_login_config_status().configured:
        raise HTTPException(status_code=503, detail="Instagram Login is not configured")
    if not verify_instagram_login_webhook_signature(raw_body, request.headers.get("X-Hub-Signature-256")):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not settings.enabled:
        return JSONResponse({"status": "disabled"})

    try:
        payload = json.loads(raw_body)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    payload_object = str(payload.get("object") or "").strip().lower()
    if payload_object not in {"instagram"}:
        return JSONResponse(
            {
                "status": "ignored",
                "reason": "unsupported_object",
                "object": payload_object,
                "accepted": 0,
            }
        )

    app_config = get_meta_app_configs()[APP_A_KEY]
    resolved_events = await resolve_registry_events(
        payload,
        app_config=app_config,
        auth_flow="instagram_login",
    )
    accepted = 0
    duplicates = 0

    async def _process_claimed(
        resolved: ResolvedMetaEvent,
        *,
        event_id: str,
        global_key: str,
        claim_handle: Any,
    ) -> None:
        from services.durable_event_claim import complete_event_claim, release_event_claim
        from services.scale.inbound_event_store import mark_inbound_state
        from services.scale.meta_ingress import mark_dm_completed, mark_dm_failed, mark_dm_processing

        evidence_surface = meta_evidence_surface(kind="meta_dm", channel=resolved.binding.channel)
        mark_dm_processing(event_id)
        try:
            from services.durable_event_claim import run_under_event_claim

            outcome = await run_under_event_claim(
                claim_handle,
                ttl_seconds=300.0,
                operation=lambda: process_meta_social_event(
                    resolved.event,
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
                    log_meta_controlled_evidence(
                        _runtime_logger,
                        event_id=event_id,
                        surface=evidence_surface,
                        outcome="provider_accepted",
                    )
                elif delivery == "duplicate_suppressed":
                    log_meta_controlled_evidence(
                        _runtime_logger,
                        event_id=event_id,
                        surface=evidence_surface,
                        outcome="duplicate_suppressed",
                    )
                else:
                    log_meta_controlled_evidence(
                        _runtime_logger,
                        event_id=event_id,
                        surface=evidence_surface,
                        outcome="failed",
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
            # Persist only a fixed exception class. Provider/AI exception text can
            # contain request identifiers or customer content.
            mark_dm_failed(event_id, f"exception:{type(exc).__name__}")
            await release_event_claim(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_dm_global_claims",
                claim_handle=claim_handle,
            )
            raise

    for resolved in resolved_events:
        event = resolved.event
        global_key = global_dm_claim_key(event)
        if not global_key.endswith(":"):
            from services.durable_event_claim import meta_claim_binding_digest, try_claim_event_handle
            from services.scale.meta_ingress import enqueue_meta_inbound_event, persist_meta_dm_accepted

            event_id, _created = persist_meta_dm_accepted(resolved, global_key=global_key)

            claim_handle = await try_claim_event_handle(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                ttl_seconds=300.0,
                firestore_collection="meta_social_dm_global_claims",
                firestore_claim_metadata={
                    "binding_id_sha256": meta_claim_binding_digest(resolved.binding.binding_id),
                    "inbound_event_id": event_id,
                },
                meta_binding_id=resolved.binding.binding_id,
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
            dispatch = enqueue_meta_inbound_event(event_id, claim_handle=claim_handle)
            log_meta_controlled_evidence(
                _runtime_logger,
                event_id=event_id,
                surface=meta_evidence_surface(kind="meta_dm", channel=resolved.binding.channel),
                outcome="instagram_login_authenticated",
            )
            if dispatch == "inline":
                _track_task(
                    asyncio.create_task(
                        _process_claimed(
                            resolved,
                            event_id=event_id,
                            global_key=global_key,
                            claim_handle=claim_handle,
                        )
                    )
                )
            accepted += 1

    comment_accepted = 0
    comment_duplicates = 0
    raw_comment_changes = count_raw_comment_changes(payload)
    resolved_comment_events = resolve_registry_comment_events(
        payload,
        app_config=app_config,
        auth_flow="instagram_login",
    )
    if raw_comment_changes and not resolved_comment_events:
        drop = summarize_comment_resolve_drops(
            payload,
            app_config=app_config,
            auth_flow="instagram_login",
        )
        _runtime_logger.warning(
            "[meta-comment] events_dropped object=%s raw=%d resolved=0 bindings=%d reasons=%s auth_flow=instagram_login",
            payload_object,
            drop["raw_comment_changes"],
            drop["active_bindings"],
            drop["skip_reasons"],
        )

    async def _process_comment_claimed(
        resolved: ResolvedMetaCommentEvent,
        *,
        event_id: str,
        global_key: str,
        claim_handle: Any,
    ) -> None:
        from services.durable_event_claim import complete_event_claim, release_event_claim
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
            from services.durable_event_claim import run_under_event_claim

            result = await run_under_event_claim(
                claim_handle,
                ttl_seconds=300.0,
                operation=lambda: process_meta_comment_event(resolved, inbound_event_id=event_id),
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
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=evidence_surface,
                    outcome="provider_accepted",
                )
            elif result.status == "ignored" and result.reason == "already_replied":
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=evidence_surface,
                    outcome="duplicate_suppressed",
                )
            else:
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=evidence_surface,
                    outcome="failed",
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
            mark_dm_failed(event_id, f"exception:{type(exc).__name__}")
            await release_event_claim(
                GLOBAL_COMMENT_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_comment_global_claims",
                claim_handle=claim_handle,
            )
            raise

    for resolved_comment in resolved_comment_events:
        global_key = global_comment_claim_key(resolved_comment.event)
        if not global_key.endswith(":"):
            from services.durable_event_claim import meta_claim_binding_digest, try_claim_event_handle
            from services.scale.meta_ingress import enqueue_meta_inbound_event, persist_meta_comment_accepted

            event_id, _created = persist_meta_comment_accepted(resolved_comment, global_key=global_key)

            claim_handle = await try_claim_event_handle(
                GLOBAL_COMMENT_CLAIM_NAMESPACE,
                global_key,
                ttl_seconds=300.0,
                firestore_collection="meta_social_comment_global_claims",
                firestore_claim_metadata={
                    "binding_id_sha256": meta_claim_binding_digest(resolved_comment.binding.binding_id),
                    "inbound_event_id": event_id,
                },
                meta_binding_id=resolved_comment.binding.binding_id,
            )
            if claim_handle is None:
                comment_duplicates += 1
                log_meta_controlled_evidence(
                    _runtime_logger,
                    event_id=event_id,
                    surface=meta_evidence_surface(kind="meta_comment", channel=resolved_comment.binding.channel),
                    outcome="duplicate_suppressed",
                )
                continue
            dispatch = enqueue_meta_inbound_event(event_id, claim_handle=claim_handle)
            log_meta_controlled_evidence(
                _runtime_logger,
                event_id=event_id,
                surface=meta_evidence_surface(kind="meta_comment", channel=resolved_comment.binding.channel),
                outcome="instagram_login_authenticated",
            )
            if dispatch == "inline":
                _track_task(
                    asyncio.create_task(
                        _process_comment_claimed(
                            resolved_comment,
                            event_id=event_id,
                            global_key=global_key,
                            claim_handle=claim_handle,
                        )
                    )
                )
            comment_accepted += 1

    _runtime_logger.info(
        "[instagram-login] webhook_authenticated object=%s parsed=%d accepted=%d duplicates=%d comments=%d",
        payload_object,
        len(resolved_events),
        accepted,
        duplicates,
        comment_accepted,
    )
    return JSONResponse(
        {
            "status": "received",
            "accepted": accepted,
            "duplicates": duplicates,
            "comments_accepted": comment_accepted,
            "comments_duplicates": comment_duplicates,
        }
    )
