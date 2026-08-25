"""TikTok Business Messaging — implemented but capability-gated until official approval/scopes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from db.session import whatsapp_session
from services.cm.actions import ACTION_TIKTOK_DM, action_enabled, load_actions_section
from services.credit_ai_gate import ai_generation_blocked
from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
from services.social_user_id import compose_social_user_id
from services.tiktok_business.errors import TikTokCapabilityGatedError
from services.tiktok_business.http_client import tiktok_request
from services.tiktok_business.oauth import ensure_fresh_token
from services.tiktok_business.repository import TikTokRepository
from services.tiktok_business.repository_content import TikTokContentRepository
from services.tiktok_business.scopes import messaging_read_ready, messaging_send_ready


async def send_business_message(
    *, access_token: str, business_id: str, conversation_id: str, text: str
) -> dict[str, Any]:
    return await tiktok_request(
        method="POST",
        path="/business/message/send/",
        access_token=access_token,
        json_body={
            "business_id": business_id,
            "recipient_type": "CONVERSATION",
            "recipient": conversation_id,
            "message_type": "TEXT",
            "text": {"body": text},
        },
    )


async def handle_messaging_webhook(
    *, payload: dict[str, Any], content: dict[str, Any], event_name: str, event_id: str
) -> dict[str, Any]:
    user_openid = str(payload.get("user_openid") or payload.get("business_id") or "").strip()
    conversation_id = str(content.get("conversation_id") or "").strip()
    if not user_openid or not conversation_id:
        return {"accepted": 1, "ignored": True, "reason": "incomplete_messaging_payload"}

    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        connection = repo.get_by_open_id_active(user_openid)
        if connection is None:
            session.commit()
            return {"accepted": 1, "ignored": True, "reason": "unknown_business"}
        if not messaging_read_ready(connection.granted_scopes):
            connection.dm_capability = "permission_pending"
            session.commit()
            return {"accepted": 1, "gated": True, "reason": "messaging_permission_pending"}
        content_repo = TikTokContentRepository(session)
        from_user = str(content.get("from") or content.get("sender") or content.get("unique_identifier") or "")
        text = str(content.get("text") or content.get("message") or "")
        provider_mid = str(content.get("message_id") or event_id)
        conv = content_repo.upsert_conversation(
            tenant_id=connection.tenant_id,
            connection_id=connection.id,
            conversation_id=conversation_id,
            customer_open_id=from_user or conversation_id,
            username=str(content.get("display_name") or ""),
            avatar_url=str(content.get("profile_image") or ""),
            preview=text[:255],
            at=datetime.now(UTC),
            increment_unread=event_name in {"im_receive_msg", "direct_message"},
        )
        _msg, created = content_repo.insert_message(
            tenant_id=connection.tenant_id,
            connection_id=connection.id,
            conversation_row_id=conv.id,
            provider_message_id=provider_mid,
            direction="inbound" if event_name != "im_send_msg" else "outbound",
            text=text,
            tiktok_request_id=str(payload.get("request_id") or ""),
        )
        session.commit()
        snapshot = {
            "tenant_id": connection.tenant_id,
            "connection_id": connection.id,
            "conversation_id": conversation_id,
            "provider_message_id": provider_mid,
            "customer_open_id": from_user,
            "text": text,
            "created": created,
            "event_name": event_name,
        }

    if snapshot["event_name"] in {"im_receive_msg", "direct_message"} and snapshot["created"] and snapshot["text"]:
        await _maybe_ai_dm(snapshot)
        await _mirror_live_chat(snapshot)
    return {"accepted": 1, "gated": False}


async def _maybe_ai_dm(snapshot: dict[str, Any]) -> None:
    tenant_id = snapshot["tenant_id"]
    actions = load_actions_section(tenant_id)
    if not action_enabled(actions, ACTION_TIKTOK_DM):
        return
    if ai_generation_blocked(tenant_id):
        return
    from services.job_queue import job_queue
    from services.omnichannel.accept import accept_and_enqueue
    from services.omnichannel.contract import NormalizedInbound
    from services.omnichannel.store import payload_hash
    from services.queues.config import redis_required

    if redis_required() and getattr(job_queue, "production_ready", False):
        event = NormalizedInbound(
            provider_event_id=str(snapshot.get("provider_message_id") or snapshot.get("conversation_id") or "")[:128],
            tenant_id=tenant_id,
            account_id=str(snapshot.get("connection_id") or ""),
            channel="tiktok",
            surface="dm",
            conversation_key=f"{tenant_id}:tiktok:{snapshot.get('conversation_id')}",
            provider_timestamp=datetime.now(UTC).timestamp(),
            payload_hash=payload_hash(snapshot),
            payload=dict(snapshot),
        )
        accept_and_enqueue(event)
        return
    with whatsapp_session() as session:
        repo = TikTokRepository(session)
        connection = repo.get_connection(snapshot["connection_id"], tenant_id=tenant_id)
        if connection is None or not messaging_send_ready(connection.granted_scopes):
            return
        token = await ensure_fresh_token(repo, connection)
        open_id = connection.open_id
        session.commit()
    outcome = await run_customer_reply_v2_dm(
        tenant_id=tenant_id,
        message=str(snapshot["text"]),
        channel="tiktok",
        provider_sender_id=str(snapshot.get("customer_open_id") or ""),
    )
    reply = str(getattr(outcome, "reply", None) or "").strip()
    if getattr(outcome, "stop", False) or not reply:
        return
    published = await send_business_message(
        access_token=token,
        business_id=open_id,
        conversation_id=str(snapshot["conversation_id"]),
        text=reply,
    )
    with whatsapp_session() as session:
        content_repo = TikTokContentRepository(session)
        conv = content_repo.upsert_conversation(
            tenant_id=tenant_id,
            connection_id=snapshot["connection_id"],
            conversation_id=str(snapshot["conversation_id"]),
            customer_open_id=str(snapshot.get("customer_open_id") or ""),
            preview=reply[:255],
            at=datetime.now(UTC),
        )
        content_repo.insert_message(
            tenant_id=tenant_id,
            connection_id=snapshot["connection_id"],
            conversation_row_id=conv.id,
            provider_message_id=str(published.get("message_id") or uuid.uuid4()),
            direction="outbound",
            text=reply,
            delivery_status="sent",
            tiktok_request_id=str(published.get("request_id") or ""),
        )
        session.commit()


async def _mirror_live_chat(snapshot: dict[str, Any]) -> None:
    try:
        from utils.utils import save_conversation_message_to_firestore

        user_id = compose_social_user_id(
            tenant_id=str(snapshot["tenant_id"]),
            channel="tiktok",
            asset_id=str(snapshot["connection_id"]),
            sender_id=str(snapshot.get("customer_open_id") or snapshot["conversation_id"]),
        )
        await save_conversation_message_to_firestore(
            user_id,
            "user",
            str(snapshot.get("text") or ""),
            conversation_id=str(snapshot["conversation_id"]),
            metadata={"channel": "tiktok", "tenant_id": snapshot["tenant_id"]},
        )
    except Exception:
        return


def assert_messaging_enabled(granted: Any) -> None:
    if not messaging_send_ready(granted):
        raise TikTokCapabilityGatedError(
            "TikTok Business Messaging is pending TikTok approval. Comments work with Account Comment scopes."
        )
