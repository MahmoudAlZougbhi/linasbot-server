"""App-level TikTok COMMENT webhook registration. Covers every public video on connected accounts."""

from __future__ import annotations

from typing import Any

from services.tiktok_business.config import require_tiktok_settings
from services.tiktok_business.errors import TikTokApiError
from services.tiktok_business.http_client import tiktok_request

COMMENT_WEBHOOK_EVENT_TYPE = "COMMENT"


async def ensure_comment_webhook_registered() -> dict[str, Any]:
    settings = require_tiktok_settings()
    wanted = settings.webhook_callback_url
    auth = {"app_id": settings.client_key, "secret": settings.client_secret}
    try:
        current = await tiktok_request(
            method="GET",
            path="/business/webhook/list/",
            params={**auth, "event_type": COMMENT_WEBHOOK_EVENT_TYPE},
        )
    except TikTokApiError:
        current = {}
    existing = str(current.get("callback_url") or current.get("callbackUrl") or "").strip()
    if existing == wanted:
        return {"ok": True, "already": True, "event_type": COMMENT_WEBHOOK_EVENT_TYPE}
    await tiktok_request(
        method="POST",
        path="/business/webhook/update/",
        json_body={
            **auth,
            "event_type": COMMENT_WEBHOOK_EVENT_TYPE,
            "callback_url": wanted,
        },
    )
    return {"ok": True, "updated": True, "event_type": COMMENT_WEBHOOK_EVENT_TYPE}
