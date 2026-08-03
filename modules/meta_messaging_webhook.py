"""Public Meta webhook for Facebook Page Messenger and Instagram professional DMs."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from modules.core import app
from services.meta_messaging import (
    InMemoryMessageDeduper,
    get_meta_messaging_settings,
    parse_meta_messaging_events,
    verify_meta_signature,
)
from services.social_messaging_processor import process_meta_social_event

_message_deduper = InMemoryMessageDeduper(ttl_seconds=300.0)
_background_tasks: set[asyncio.Task] = set()
_runtime_logger = logging.getLogger("uvicorn.error")


def _track_task(task: asyncio.Task) -> None:
    _background_tasks.add(task)

    def _done(completed: asyncio.Task) -> None:
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
    if not settings.verify_token:
        raise HTTPException(status_code=503, detail="Meta webhook verify token is not configured")
    if mode == "subscribe" and token == settings.verify_token and challenge is not None:
        return PlainTextResponse(challenge)
    raise HTTPException(status_code=403, detail="Webhook verification failed")


@app.post("/webhook/meta-messaging")
async def receive_meta_messaging_webhook(request: Request) -> Any:
    settings = get_meta_messaging_settings()
    raw_body = await request.body()

    # Never acknowledge an unauthenticated POST as valid. A missing server-side
    # secret is a readiness failure; a missing/wrong request signature is 401.
    if not settings.app_secret:
        raise HTTPException(status_code=503, detail="Meta App Secret is not configured")
    if not verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"), settings.app_secret):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    if not settings.enabled:
        return JSONResponse({"status": "disabled"})
    if (
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

    events = parse_meta_messaging_events(
        payload,
        instagram_account_id=settings.instagram_account_id,
        page_id=settings.page_id,
    )
    accepted = 0
    duplicates = 0

    async def _process_claimed(event: dict) -> None:
        from services.durable_event_claim import complete_event_claim, release_event_claim

        mid = str(event.get("message_id") or "")
        channel = str(event.get("channel") or "unknown").strip().lower()
        _runtime_logger.info("[meta-social] event_processing_started channel=%s", channel)
        try:
            await process_meta_social_event(event, settings)
            await complete_event_claim(
                "meta_messaging_mid",
                mid,
                firestore_collection="meta_messaging_mid_claims",
            )
            _runtime_logger.info("[meta-social] event_processing_completed channel=%s", channel)
        except Exception as exc:
            _runtime_logger.error(
                "[meta-social] event_processing_failed channel=%s type=%s",
                channel,
                type(exc).__name__,
            )
            await release_event_claim(
                "meta_messaging_mid",
                mid,
                firestore_collection="meta_messaging_mid_claims",
            )
            raise

    for event in events:
        mid = str(event.get("message_id") or "")
        # Fast local reject for same-process redeliveries
        if not _message_deduper.claim(mid):
            duplicates += 1
            continue
        from services.durable_event_claim import try_claim_event

        claimed = await try_claim_event(
            "meta_messaging_mid",
            mid,
            ttl_seconds=300.0,
            firestore_collection="meta_messaging_mid_claims",
        )
        if not claimed:
            duplicates += 1
            continue
        _track_task(asyncio.create_task(_process_claimed(event)))
        accepted += 1
    channel_counts = {
        "facebook": sum(str(event.get("channel") or "") == "facebook" for event in events),
        "instagram": sum(str(event.get("channel") or "") == "instagram" for event in events),
    }
    _runtime_logger.info(
        "[meta-social] webhook_authenticated object=%s parsed=%d accepted=%d duplicates=%d facebook=%d instagram=%d",
        payload_object,
        len(events),
        accepted,
        duplicates,
        channel_counts["facebook"],
        channel_counts["instagram"],
    )
    return JSONResponse(
        {
            "status": "received",
            "accepted": accepted,
            "duplicates": duplicates,
        }
    )
