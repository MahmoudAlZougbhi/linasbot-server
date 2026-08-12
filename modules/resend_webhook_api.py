"""Resend delivery webhooks — signature verify + idempotent event store."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from modules.core import app
from services.email_delivery_store import email_delivery_store
from services.resend_webhook_verify import WebhookSignatureError, verify_resend_webhook


@app.post("/api/webhooks/resend")
async def resend_webhook(request: Request) -> Any:
    raw = await request.body()
    try:
        payload = verify_resend_webhook(payload=raw, headers=request.headers)
    except WebhookSignatureError as exc:
        raise HTTPException(status_code=400, detail="Invalid webhook") from exc

    svix_id = (request.headers.get("svix-id") or "").strip()
    if not svix_id:
        raise HTTPException(status_code=400, detail="Missing event id")

    result = email_delivery_store.record_event(svix_id=svix_id, payload=payload)
    record = result.get("record") or {}
    return JSONResponse(
        content={
            "ok": True,
            "duplicate": bool(result.get("duplicate")),
            "state": record.get("state"),
            "type": record.get("type"),
        }
    )
