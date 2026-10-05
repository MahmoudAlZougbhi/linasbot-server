"""Legacy WhatsApp /webhook entry: Meta verify plus an ignore ack.

Inbound customer AI runs only through Terra on the Cloud and Meta messaging
webhooks. This route must not import or call the retired process/parse/photo/voice chain.
"""

from __future__ import annotations

import hmac
import os
import time
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from modules.core import app

_last_webhook_received_at = None
_last_webhook_parsed_at = None
_last_webhook_user_id = None


def get_webhook_debug_status() -> Any:
    """Return last webhook timestamps for /api/debug/webhook-status."""
    import datetime

    return {
        "last_received_at": _last_webhook_received_at,
        "last_received_iso": datetime.datetime.fromtimestamp(_last_webhook_received_at).isoformat()
        if _last_webhook_received_at
        else None,
        "last_parsed_at": _last_webhook_parsed_at,
        "last_parsed_user_id": _last_webhook_user_id,
        "seconds_since_received": round(time.time() - _last_webhook_received_at, 1)
        if _last_webhook_received_at
        else None,
    }


@app.get("/webhook")
async def verify_webhook(request: Request) -> Any:
    """Endpoint for WhatsApp webhook verification."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge")

    verify_token = os.getenv("WHATSAPP_WEBHOOK_VERIFY_TOKEN")
    if not verify_token or verify_token == "YOUR_SECURE_VERIFY_TOKEN":
        raise HTTPException(status_code=500, detail="WHATSAPP_WEBHOOK_VERIFY_TOKEN must be set in .env")

    if mode == "subscribe" and token is not None and hmac.compare_digest(token, verify_token):
        print("WEBHOOK_VERIFIED")
        if challenge is None or (isinstance(challenge, str) and not challenge.strip()):
            raise HTTPException(status_code=400, detail="Invalid webhook challenge")
        try:
            return int(challenge)
        except (TypeError, ValueError) as e:
            raise HTTPException(status_code=400, detail="Invalid webhook challenge format") from e
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@app.post("/webhook")
async def receive_webhook(request: Request) -> Any:
    """Ack legacy WhatsApp posts without running customer AI.

    Facebook Messenger and Instagram DMs are handled only on /webhook/meta-messaging.
    WhatsApp Cloud inbound is /webhook/whatsapp-cloud.
    """
    global _last_webhook_received_at
    try:
        raw_body = await request.body()
        app_secret = (os.getenv("WHATSAPP_APP_SECRET") or os.getenv("META_APP_SECRET") or "").strip()
        ingest_secret = (os.getenv("WHATSAPP_WEBHOOK_INGEST_SECRET") or "").strip()
        env = (os.getenv("ENVIRONMENT") or os.getenv("ENV") or "").strip().lower()
        is_prod = env in {"prod", "production"}

        authenticated = False
        if app_secret:
            from services.integrations.meta.meta_messaging import verify_meta_signature

            if verify_meta_signature(raw_body, request.headers.get("X-Hub-Signature-256"), app_secret):
                authenticated = True
            else:
                raise HTTPException(status_code=401, detail="Invalid webhook signature")
        elif ingest_secret:
            provided = (request.headers.get("X-Webhook-Secret") or "").strip()
            if not provided or not hmac.compare_digest(provided, ingest_secret):
                raise HTTPException(status_code=401, detail="Invalid webhook secret")
            authenticated = True
        elif is_prod:
            raise HTTPException(
                status_code=503,
                detail="WhatsApp webhook authentication is not configured",
            )
        else:
            authenticated = True

        _last_webhook_received_at = time.time()
        print(
            f"WhatsApp webhook POST received ({len(raw_body)} bytes) auth={authenticated} — "
            "inbound AI disabled"
        )
        return JSONResponse(
            status_code=200,
            content={
                "status": "ignored",
                "reason": "whatsapp_inbound_ai_disabled",
                "accepted": 0,
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        print(f"CRITICAL ERROR acknowledging WhatsApp webhook: {e}")
        return JSONResponse(
            status_code=200,
            content={
                "status": "ignored",
                "reason": "whatsapp_inbound_ai_disabled",
                "accepted": 0,
            },
        )
