"""TikTok comment/DM delivery. DMs stay capability-gated."""

from __future__ import annotations

from typing import Any

from db.session import whatsapp_session
from services.omnichannel.gates import tiktok_dm_live_allowed
from services.tiktok_business.oauth import ensure_fresh_token
from services.tiktok_business.repository import TikTokRepository


async def deliver_tiktok(snapshot: dict[str, Any]) -> dict[str, Any]:
    surface = str(snapshot.get("surface") or "comment")
    text = str(snapshot.get("canonical_body") or "")
    tenant_id = str(snapshot["tenant_id"])
    connection_id = str(snapshot.get("account_id") or "")
    with whatsapp_session(require=True) as session:
        repo = TikTokRepository(session)
        connection = repo.get_connection(connection_id, tenant_id=tenant_id)
        if connection is None:
            return {"http_status": 404, "error": "missing_connection", "submitted": False}
        if surface == "dm":
            allowed, reason = tiktok_dm_live_allowed(connection)
            if not allowed:
                return {"http_status": 403, "error": reason, "submitted": False, "code": "permission_pending"}
        token = await ensure_fresh_token(repo, connection)
        open_id = connection.open_id
        session.commit()

    if surface == "dm":
        from services.tiktok_business.messaging import send_business_message

        conv = str((snapshot.get("conversation_key") or "").rsplit(":", 1)[-1])
        try:
            payload = await send_business_message(
                access_token=token,
                business_id=open_id,
                conversation_id=conv,
                text=text,
            )
        except Exception as exc:
            name = type(exc).__name__
            reset = name in {"ConnectionError", "ConnectionResetError", "ConnectError", "ConnectTimeout"}
            return {
                "error": name,
                "submitted": False,
                "reset_before_submit": reset,
                "malformed": "JSON" in name or "json" in str(exc).lower(),
            }
        return {
            "http_status": 200,
            "submitted": True,
            "request_id": str((payload or {}).get("request_id") or ""),
            "message_id": str((payload or {}).get("message_id") or ""),
        }

    from services.tiktok_business.comment_publish import create_comment_reply

    parts = str(snapshot.get("conversation_key") or "").split(":")
    comment_id = parts[-1] if parts else ""
    video_id = str(snapshot.get("item_id") or snapshot.get("video_id") or "")
    if not video_id and len(parts) >= 2:
        video_id = parts[-2]
    try:
        payload = await create_comment_reply(
            access_token=token,
            business_id=open_id,
            video_id=video_id,
            comment_id=comment_id,
            text=text,
        )
    except Exception as exc:
        name = type(exc).__name__
        reset = name in {"ConnectionError", "ConnectionResetError", "ConnectError", "ConnectTimeout"}
        return {"error": name, "submitted": False, "reset_before_submit": reset}
    return {
        "http_status": 200,
        "submitted": True,
        "request_id": str((payload or {}).get("request_id") or ""),
        "message_id": str((payload or {}).get("comment_id") or ""),
    }
