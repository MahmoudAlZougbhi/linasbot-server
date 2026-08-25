"""Operator outbound text for TikTok Live Chat threads."""

from __future__ import annotations

from typing import Any

from services.tiktok_business.errors import TikTokCapabilityGatedError
from services.tiktok_business.messaging import send_business_message
from services.tiktok_business.oauth import ensure_fresh_token
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.scopes import messaging_send_ready


def is_tiktok_live_chat_user(user_id: str | None) -> bool:
    try:
        parse_tiktok_live_chat_user_id(str(user_id or ""))
        return True
    except ValueError:
        return False


def parse_tiktok_live_chat_user_id(user_id: str) -> tuple[str, str | None, str | None]:
    """Return (sender_id, connection_id, embedded_tenant_id)."""
    parts = [p.strip() for p in str(user_id or "").split(":") if p.strip()]
    if len(parts) == 2 and parts[0].lower() == "tiktok":
        return parts[1], None, None
    if len(parts) == 3 and parts[0].lower() == "tiktok":
        return parts[2], parts[1], None
    if len(parts) >= 4 and parts[1].lower() == "tiktok":
        return parts[3], parts[2], parts[0]
    raise ValueError("unsupported_tiktok_live_chat_user_id")


async def deliver_live_chat_tiktok_operator_text(
    *,
    tenant_id: str | None,
    user_id: str,
    conversation_id: str,
    text: str,
) -> dict[str, Any]:
    sender_id, connection_id, embedded_tenant = parse_tiktok_live_chat_user_id(user_id)
    tenant = str(tenant_id or embedded_tenant or "linas").strip()
    if not tenant:
        return {"success": False, "error": "tenant_required_for_tiktok_send", "delivered": False}
    conv_id = str(conversation_id or sender_id or "").strip()
    if not conv_id:
        return {"success": False, "error": "tiktok_conversation_required", "delivered": False}
    if not text.strip():
        return {"success": False, "error": "empty_message", "delivered": False}

    from db.session import whatsapp_session

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        connection = None
        if connection_id:
            connection = repo.get_connection(connection_id, tenant_id=tenant)
        if connection is None:
            connection = repo.get_active_for_tenant(tenant)
        if connection is None or connection.tenant_id != tenant:
            return {"success": False, "error": "tiktok_connection_not_found", "delivered": False}
        if not messaging_send_ready(connection.granted_scopes):
            return {
                "success": False,
                "error": "tiktok_messaging_permission_pending",
                "delivered": False,
                "blocked": True,
            }
        try:
            token = await ensure_fresh_token(repo, connection)
            published = await send_business_message(
                access_token=token,
                business_id=connection.open_id,
                conversation_id=conv_id,
                text=text.strip(),
            )
        except TikTokCapabilityGatedError as exc:
            return {
                "success": False,
                "error": str(exc)[:180],
                "delivered": False,
                "blocked": True,
            }
        except Exception as exc:
            return {"success": False, "error": str(exc)[:180], "delivered": False}
        message_id = str(
            (published or {}).get("message_id")
            or (published or {}).get("data", {}).get("message_id")
            or ""
        ).strip()
        return {
            "success": True,
            "delivered": True,
            "provider_message_id": message_id or None,
            "channel": "tiktok",
        }


def tiktok_operator_media_not_supported() -> dict[str, Any]:
    return {
        "success": False,
        "delivered": False,
        "error": "TikTok operator media replies are not supported by the TikTok Business Messaging API yet",
        "channel": "tiktok",
    }
