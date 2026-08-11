"""Official WhatsApp Cloud API webhook — App A signature, tenant from phone_number_id binding."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from modules.core import app
from services.meta_app_registry import APP_A_KEY, get_meta_app_configs, verify_any_meta_challenge_token
from services.meta_messaging import verify_meta_signature
from services.whatsapp_cloud.config import get_whatsapp_cloud_flags
from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.webhook_processor import process_whatsapp_cloud_webhook


@app.get("/webhook/whatsapp-cloud")
async def verify_whatsapp_cloud_webhook(request: Request) -> Any:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")
    if mode == "subscribe" and verify_any_meta_challenge_token(token):
        if challenge is None or (isinstance(challenge, str) and not str(challenge).strip()):
            raise HTTPException(status_code=400, detail="Invalid webhook challenge")
        return PlainTextResponse(content=str(challenge))
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook/whatsapp-cloud")
async def receive_whatsapp_cloud_webhook(request: Request) -> Any:
    raw_body = await request.body()
    configs = get_meta_app_configs()
    app_a = configs.get(APP_A_KEY)
    if app_a is None or not app_a.enabled or not app_a.app_secret:
        emit_wa_event("signature_reject", reason="app_a_unavailable")
        raise HTTPException(status_code=503, detail="WhatsApp Cloud webhook not configured")

    sig = request.headers.get("X-Hub-Signature-256")
    if not verify_meta_signature(raw_body, sig, app_a.app_secret):
        emit_wa_event("signature_rejection")
        raise HTTPException(status_code=403, detail="Invalid signature")

    flags = get_whatsapp_cloud_flags()
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON") from None
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")

    if not flags.webhook_side_effects_enabled:
        return JSONResponse(content={"status": "ignored", "reason": "webhook_side_effects_disabled", "accepted": 0})

    result = await process_whatsapp_cloud_webhook(raw_body=raw_body, payload=payload)
    return JSONResponse(content=result)
