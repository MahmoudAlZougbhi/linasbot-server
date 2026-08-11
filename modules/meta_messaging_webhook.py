"""Public Meta webhook for Facebook Page Messenger and Instagram professional DMs."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from modules.core import app
from services.meta_app_registry import (
    APP_A_KEY,
    MetaAssetBinding,
    MetaChannel,
    identify_signed_meta_app,
    meta_multi_app_registry_enabled,
    verify_any_meta_challenge_token,
)
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
from services.meta_messaging import (
    InMemoryMessageDeduper,
    get_meta_messaging_settings,
    parse_meta_messaging_events,
    verify_meta_signature,
)
from services.meta_multi_app_router import ResolvedMetaEvent, resolve_registry_events
from services.social_messaging_processor import process_meta_social_event

_message_deduper = InMemoryMessageDeduper(ttl_seconds=300.0)
_comment_deduper = InMemoryMessageDeduper(ttl_seconds=600.0)
_background_tasks: set[asyncio.Task[None]] = set()
_runtime_logger = logging.getLogger("uvicorn.error")


def _legacy_binding(settings: Any, channel: str) -> MetaAssetBinding:
    """Represent the legacy single-app route without changing persisted state."""

    normalized_channel: MetaChannel = "instagram" if channel == "instagram" else "facebook"
    asset_id = settings.instagram_account_id if normalized_channel == "instagram" else settings.page_id
    return MetaAssetBinding(
        binding_id="legacy-single-app",
        tenant_id="linas",
        channel=normalized_channel,
        asset_id=asset_id,
        page_id=settings.page_id,
        instagram_account_id=settings.instagram_account_id,
        app_key=APP_A_KEY,
        credential_id="legacy-environment",
        status="active",
        generation=1,
        created_at=0.0,
        updated_at=0.0,
    )


def _track_task(task: asyncio.Task[None]) -> None:
    _background_tasks.add(task)

    def _done(completed: asyncio.Task[None]) -> None:
        _background_tasks.discard(completed)
        try:
            completed.result()
        except Exception as exc:
            _runtime_logger.error(
                "[meta-social] background_processing_failed type=%s",
                type(exc).__name__,
            )

    task.add_done_callback(_done)


@app.get("/webhook/meta-messaging")
async def verify_meta_messaging_webhook(request: Request) -> Any:
    settings = get_meta_messaging_settings()
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    registry_enabled = meta_multi_app_registry_enabled()
    if not settings.verify_token and not registry_enabled:
        raise HTTPException(status_code=503, detail="Meta webhook verify token is not configured")
    token_ok = verify_any_meta_challenge_token(token) if registry_enabled else token == settings.verify_token
    if mode == "subscribe" and token_ok and challenge is not None:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhook/meta-messaging")
async def receive_meta_messaging_webhook(request: Request) -> Any:
    settings = get_meta_messaging_settings()
    raw_body = await request.body()

    # Never acknowledge an unauthenticated POST as valid. A missing server-side
    # secret is a readiness failure; a missing/wrong request signature is 401.
    registry_enabled = meta_multi_app_registry_enabled()
    signed_app = None
    if registry_enabled:
        signed_app = identify_signed_meta_app(raw_body, request.headers.get("X-Hub-Signature-256"))
        if signed_app is None:
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
    else:
        if not settings.app_secret:
            raise HTTPException(status_code=503, detail="Meta App Secret is not configured")
        if not verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"), settings.app_secret):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not settings.enabled:
        return JSONResponse({"status": "disabled"})
    if not registry_enabled and (
        not settings.app_secret
        or not settings.page_access_token
        or not settings.page_id
        or not settings.instagram_account_id
    ):
        raise HTTPException(status_code=503, detail="Meta messaging credentials are incomplete")

    try:
        payload = json.loads(raw_body)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    payload_object = str(payload.get("object") or "").strip().lower()
    # Meta WhatsApp Cloud events must never enter the social AI pipeline.
    if payload_object == "whatsapp_business_account" or payload_object == "whatsapp":
        return JSONResponse(
            {
                "status": "ignored",
                "reason": "whatsapp_inbound_not_supported",
                "accepted": 0,
            }
        )
    if payload_object not in {"page", "instagram"}:
        return JSONResponse(
            {
                "status": "ignored",
                "reason": "unsupported_object",
                "object": payload_object,
                "accepted": 0,
            }
        )

    resolved_events: list[ResolvedMetaEvent] = []
    if registry_enabled:
        if signed_app is None:  # pragma: no cover - guarded above
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
        resolved_events = await resolve_registry_events(
            payload,
            app_config=signed_app,
            auth_flow="facebook_login",
        )
    else:
        legacy_events = parse_meta_messaging_events(
            payload,
            instagram_account_id=settings.instagram_account_id,
            page_id=settings.page_id,
        )
        resolved_events = [
            ResolvedMetaEvent(
                event=event,
                settings=settings,
                binding=_legacy_binding(settings, str(event.get("channel") or "facebook")),
            )
            for event in legacy_events
        ]
    accepted = 0
    duplicates = 0

    async def _process_claimed(resolved: ResolvedMetaEvent) -> None:
        from services.durable_event_claim import complete_event_claim, release_event_claim

        event = resolved.event
        global_key = global_dm_claim_key(event)
        channel = str(event.get("channel") or "unknown").strip().lower()
        _runtime_logger.info(
            "[meta-social] event_processing_started channel=%s app_key=%s",
            channel,
            resolved.settings.app_key,
        )
        try:
            await process_meta_social_event(event, resolved.settings)
            await complete_event_claim(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_dm_global_claims",
            )
            _runtime_logger.info(
                "[meta-social] event_processing_completed channel=%s app_key=%s",
                channel,
                resolved.settings.app_key,
            )
        except Exception as exc:
            _runtime_logger.error(
                "[meta-social] event_processing_failed channel=%s type=%s",
                channel,
                type(exc).__name__,
            )
            await release_event_claim(
                GLOBAL_DM_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_dm_global_claims",
            )
            raise

    for resolved in resolved_events:
        event = resolved.event
        global_key = global_dm_claim_key(event)
        if global_key.endswith(":"):
            continue
        if not _message_deduper.claim(global_key):
            duplicates += 1
            continue
        from services.durable_event_claim import try_claim_event

        claimed = await try_claim_event(
            GLOBAL_DM_CLAIM_NAMESPACE,
            global_key,
            ttl_seconds=300.0,
            firestore_collection="meta_social_dm_global_claims",
        )
        if not claimed:
            duplicates += 1
            continue
        _track_task(asyncio.create_task(_process_claimed(resolved)))
        accepted += 1

    comment_accepted = 0
    comment_duplicates = 0
    resolved_comment_events: list[ResolvedMetaCommentEvent] = []
    raw_comment_changes = count_raw_comment_changes(payload)
    if registry_enabled and signed_app is not None and signed_app.key == APP_A_KEY:
        # App A Instagram object webhooks (including comments) land here.
        # Do not restrict to facebook_login: a Direct Instagram Login binding for the
        # same IG professional account must be eligible when Meta delivers comments
        # on this callback. Selection still prefers a comments-ready instagram_login row.
        from services.meta_instagram_login_config import AuthFlow

        comment_auth_flow: AuthFlow | None = None if payload_object == "instagram" else "facebook_login"
        resolved_comment_events = resolve_registry_comment_events(
            payload,
            app_config=signed_app,
            auth_flow=comment_auth_flow,
        )
        if raw_comment_changes and not resolved_comment_events:
            drop = summarize_comment_resolve_drops(
                payload,
                app_config=signed_app,
                auth_flow=comment_auth_flow,
            )
            _runtime_logger.warning(
                "[meta-comment] events_dropped object=%s raw=%d resolved=0 bindings=%d reasons=%s",
                payload_object,
                drop["raw_comment_changes"],
                drop["active_bindings"],
                drop["skip_reasons"],
            )

    async def _process_comment_claimed(resolved: ResolvedMetaCommentEvent) -> None:
        from services.durable_event_claim import complete_event_claim, release_event_claim

        global_key = global_comment_claim_key(resolved.event)
        _runtime_logger.info(
            "[meta-comment] event_processing_started channel=%s tenant=%s auth_flow=%s",
            resolved.binding.channel,
            resolved.binding.tenant_id,
            resolved.binding.auth_flow,
        )
        try:
            result = await process_meta_comment_event(resolved)
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
            _runtime_logger.error(
                "[meta-comment] event_processing_failed channel=%s type=%s",
                resolved.binding.channel,
                type(exc).__name__,
            )
            await release_event_claim(
                GLOBAL_COMMENT_CLAIM_NAMESPACE,
                global_key,
                firestore_collection="meta_social_comment_global_claims",
            )
            raise

    for resolved_comment in resolved_comment_events:
        global_key = global_comment_claim_key(resolved_comment.event)
        if global_key.endswith(":"):
            continue
        if not _comment_deduper.claim(global_key):
            comment_duplicates += 1
            continue
        from services.durable_event_claim import try_claim_event

        claimed = await try_claim_event(
            GLOBAL_COMMENT_CLAIM_NAMESPACE,
            global_key,
            ttl_seconds=86400.0,
            firestore_collection="meta_social_comment_global_claims",
        )
        if not claimed:
            comment_duplicates += 1
            continue
        _track_task(asyncio.create_task(_process_comment_claimed(resolved_comment)))
        comment_accepted += 1

    channel_counts = {
        "facebook": sum(str(item.event.get("channel") or "") == "facebook" for item in resolved_events),
        "instagram": sum(str(item.event.get("channel") or "") == "instagram" for item in resolved_events),
    }
    _runtime_logger.info(
        "[meta-social] webhook_authenticated object=%s parsed=%d accepted=%d duplicates=%d facebook=%d instagram=%d",
        payload_object,
        len(resolved_events),
        accepted,
        duplicates,
        channel_counts["facebook"],
        channel_counts["instagram"],
    )
    if resolved_comment_events or raw_comment_changes:
        auth_flows = sorted({str(item.binding.auth_flow) for item in resolved_comment_events})
        _runtime_logger.info(
            "[meta-comment] webhook_authenticated object=%s raw=%d parsed=%d accepted=%d duplicates=%d auth_flows=%s",
            payload_object,
            raw_comment_changes,
            len(resolved_comment_events),
            comment_accepted,
            comment_duplicates,
            ",".join(auth_flows) or "none",
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
