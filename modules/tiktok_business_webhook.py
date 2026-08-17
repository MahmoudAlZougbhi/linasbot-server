"""TikTok webhook receiver — signature required, fail closed without credentials."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse

from modules.core import app
from services.tiktok_business.config import get_tiktok_settings
from services.tiktok_business.errors import TikTokBusinessError
from services.tiktok_business.webhook_process import process_tiktok_webhook_payload
from services.tiktok_business.webhook_verify import verify_tiktok_signature


async def _receive(request: Request) -> Any:
    settings = get_tiktok_settings()
    if not settings.configured:
        raise HTTPException(status_code=503, detail="TikTok webhook is not configured")
    raw_body = await request.body()
    header = request.headers.get("TikTok-Signature") or request.headers.get("Tiktok-Signature") or ""
    try:
        verify_tiktok_signature(raw_body=raw_body, header=header)
    except TikTokBusinessError as exc:
        raise HTTPException(status_code=exc.http_status, detail=exc.code) from exc
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="Invalid payload")
    result = await process_tiktok_webhook_payload(raw_body=raw_body, payload=payload)
    return JSONResponse(content={"ok": True, **result})


@app.post("/webhooks/tiktok")
async def tiktok_webhook(request: Request) -> Any:
    return await _receive(request)


@app.post("/webhook/tiktok")
async def tiktok_webhook_alias(request: Request) -> Any:
    return await _receive(request)
