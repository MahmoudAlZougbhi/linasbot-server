"""TikTok webhook dispatch. Comment events cover every public video; DMs stay capability-gated."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from db.session import whatsapp_session
from services.tiktok_business.repository_content import TikTokContentRepository


def _event_id(payload: dict[str, Any], raw_body: bytes) -> str:
    explicit = str(payload.get("event_id") or payload.get("log_id") or "").strip()
    if explicit:
        return explicit[:128]
    digest = hashlib.sha256(raw_body).hexdigest()
    return digest[:128]


async def process_tiktok_webhook_payload(*, raw_body: bytes, payload: dict[str, Any]) -> dict[str, Any]:
    event_name = str(payload.get("event") or payload.get("event_type") or "").strip().lower()
    event_id = _event_id(payload, raw_body)
    content_raw = payload.get("content")
    content: dict[str, Any] = {}
    if isinstance(content_raw, dict):
        content = content_raw
    elif isinstance(content_raw, str) and content_raw.strip():
        try:
            parsed = json.loads(content_raw)
        except json.JSONDecodeError:
            parsed = {}
        if isinstance(parsed, dict):
            content = parsed

    with whatsapp_session() as session:
        content_repo = TikTokContentRepository(session)
        claimed = content_repo.claim_webhook_event(event_id=event_id, event_name=event_name or "unknown")
        if not claimed:
            session.commit()
            return {"accepted": 0, "duplicate": True}
        session.commit()

    if event_name in {"im_receive_msg", "im_send_msg", "direct_message", "im_mark_read_msg"}:
        from services.tiktok_business.messaging import handle_messaging_webhook

        return await handle_messaging_webhook(
            payload=payload, content=content, event_name=event_name, event_id=event_id
        )
    if event_name.startswith("comment."):
        from services.tiktok_business.comment_webhook import handle_comment_webhook

        return await handle_comment_webhook(payload=payload, content=content, event_name=event_name)

    # Unknown event types are acknowledged after signature + idempotency — no fake success side effects.
    return {"accepted": 1, "event": event_name or "unknown", "ignored": True}
