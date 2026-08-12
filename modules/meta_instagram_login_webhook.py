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
from services.meta_comment_replies import process_meta_comment_event
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
from services.social_messaging_processor import process_meta_social_event

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

    async def _process_claimed(resolved: ResolvedMetaEvent, *, event_id: str, global_key: str) -> None:
        from services.durable_event_claim import complete_event_claim, release_event_claim
        from services.scale.meta_ingress import mark_dm_completed, mark_dm_failed, mark_dm_processing

        mark_dm_processing(event_id)
        try:
            await process_meta_social_event(resolved.event, resolved.settings)
            mark_dm_completed(event_id)
            await complete_event_claim(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_dm_global_claims",
            )
        except Exception as exc:
            mark_dm_failed(event_id, f"{type(exc).__name__}:{exc}")
            await release_event_claim(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_dm_global_claims",
            )
            raise

    for resolved in resolved_events:
        event = resolved.event
        global_key = global_dm_claim_key(event)
        if not global_key.endswith(":"):
            if not _message_deduper.claim(global_key):
                duplicates += 1
                continue
            from services.durable_event_claim import try_claim_event
            from services.scale.meta_ingress import persist_meta_dm_accepted

            claimed = await try_claim_event(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                ttl_seconds=300.0,
                firestore_collection="meta_social_dm_global_claims",
            )
            if not claimed:
                duplicates += 1
                continue
            event_id, queued = persist_meta_dm_accepted(resolved, global_key=global_key)
            if not queued:
                _track_task(
                    asyncio.create_task(_process_claimed(resolved, event_id=event_id, global_key=global_key))
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
        resolved: ResolvedMetaCommentEvent, *, event_id: str, global_key: str
    ) -> None:
        from services.durable_event_claim import complete_event_claim, release_event_claim
        from services.scale.meta_ingress import mark_dm_completed, mark_dm_failed, mark_dm_processing

        _runtime_logger.info(
            "[meta-comment] event_processing_started channel=%s tenant=%s auth_flow=%s event_id=%s",
            resolved.binding.channel,
            resolved.binding.tenant_id,
            resolved.binding.auth_flow,
            event_id,
        )
        mark_dm_processing(event_id)
        try:
            result = await process_meta_comment_event(resolved)
            mark_dm_completed(event_id, outbound_status=f"{result.status}:{result.reason}")
            await complete_event_claim(
                GLOBAL_COMMENT_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_comment_global_claims",
            )
            _runtime_logger.info(
                "[meta-comment] event_processing_completed channel=%s status=%s reason=%s auth_flow=%s",
                resolved.binding.channel,
                result.status,
                result.reason,
                resolved.binding.auth_flow,
            )
        except Exception as exc:
            mark_dm_failed(event_id, f"{type(exc).__name__}:{exc}")
            await release_event_claim(
                GLOBAL_COMMENT_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_comment_global_claims",
            )
            raise

    for resolved_comment in resolved_comment_events:
        global_key = global_comment_claim_key(resolved_comment.event)
        if not global_key.endswith(":"):
            if not _comment_deduper.claim(global_key):
                comment_duplicates += 1
                continue
            from services.durable_event_claim import try_claim_event
            from services.scale.meta_ingress import persist_meta_comment_accepted

            claimed = await try_claim_event(
                GLOBAL_COMMENT_CLAIM_NAMESPACE,
                global_key,
                ttl_seconds=86400.0,
                firestore_collection="meta_social_comment_global_claims",
            )
            if not claimed:
                comment_duplicates += 1
                continue
            event_id, queued = persist_meta_comment_accepted(resolved_comment, global_key=global_key)
            if not queued:
                _track_task(
                    asyncio.create_task(
                        _process_comment_claimed(resolved_comment, event_id=event_id, global_key=global_key)
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
