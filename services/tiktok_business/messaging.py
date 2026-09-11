"""TikTok Business Messaging — implemented but capability-gated until official approval/scopes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from db.session import whatsapp_session
from services.cm.actions import ACTION_TIKTOK_DM, action_enabled, load_actions_section
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
        from services.tiktok_business.inbound_dm import message_text_from_content

        text = message_text_from_content(content)
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

    if snapshot["event_name"] in {"im_receive_msg", "direct_message"} and snapshot["created"]:
        from services.tiktok_business.inbound_dm import hydrate_tiktok_inbound_media

        inbound_media = await hydrate_tiktok_inbound_media(
            tenant_id=str(snapshot["tenant_id"]),
            content=content,
        )
        snapshot["inbound_media"] = inbound_media
        if snapshot["text"] or inbound_media.get("attachment_types"):
            await _maybe_ai_dm(snapshot)
            await _mirror_live_chat(snapshot)
    return {"accepted": 1, "gated": False}


async def _maybe_ai_dm(snapshot: dict[str, Any]) -> None:
    tenant_id = snapshot["tenant_id"]
    actions = load_actions_section(tenant_id)
    if not action_enabled(actions, ACTION_TIKTOK_DM):
        return
    from services.membership.generative_gate import generative_ai_blocked

    if generative_ai_blocked(tenant_id):
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
    sender = str(snapshot.get("customer_open_id") or snapshot.get("conversation_id") or "")
    inbound_mid = str(snapshot.get("provider_message_id") or snapshot.get("conversation_id") or "")
    leftover_rid = None
    from services.customer_ai.leftover_reserve import (
        capture_leftover_reply,
        release_leftover_reply,
        reserve_leftover_reply,
    )

    try:
        leftover_rid = reserve_leftover_reply(
            tenant_id=tenant_id,
            request_id=f"tiktok:{inbound_mid}",
            operation_type="tiktok_customer_reply",
            pin_ids=(inbound_mid, str(snapshot.get("conversation_id") or "")),
        )
    except PermissionError:
        return
    sent = False
    provider_mid = ""
    brain_mid = inbound_mid
    try:
        from services.customer_ai.history_ids import bind_dm_ids
        from services.customer_reply_v2.inbound_media import planner_text_from_inbound

        inbound_media = snapshot.get("inbound_media") if isinstance(snapshot.get("inbound_media"), dict) else {}
        message = planner_text_from_inbound(inbound_media, text=str(snapshot.get("text") or ""))
        if not message and inbound_media.get("attachment_types"):
            message = "Sent a message."
        conv, brain_mid = bind_dm_ids(
            conversation_id=str(snapshot.get("conversation_id") or ""),
            message_id=str(snapshot.get("provider_message_id") or ""),
            message=message,
            payload=snapshot,
        )
        outcome = await run_customer_reply_v2_dm(
            tenant_id=tenant_id,
            message=message,
            channel="tiktok",
            provider_sender_id=sender,
            user_id=compose_social_user_id(
                tenant_id=tenant_id,
                channel="tiktok",
                asset_id=str(snapshot.get("connection_id") or ""),
                sender_id=sender,
            ),
            conversation_id=conv,
            message_id=brain_mid,
            inbound_media=inbound_media or None,
        )
        reply = str(getattr(outcome, "reply", None) or "").strip()
        if getattr(outcome, "stop", False) or not reply:
            release_leftover_reply(tenant_id, leftover_rid)
            _settle_tiktok_dm_send(
                tenant_id=tenant_id,
                snapshot=snapshot,
                leftover_rid=leftover_rid,
                brain_mid=brain_mid,
                accepted=False,
            )
            return
        published = await send_business_message(
            access_token=token,
            business_id=open_id,
            conversation_id=str(snapshot["conversation_id"]),
            text=reply,
        )
        sent = True
        provider_mid = str(published.get("message_id") or "")
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
        capture_leftover_reply(
            tenant_id,
            leftover_rid,
            model_provider="tiktok",
            provider_message_id=provider_mid,
        )
        _settle_tiktok_dm_send(
            tenant_id=tenant_id,
            snapshot=snapshot,
            leftover_rid=leftover_rid,
            brain_mid=brain_mid,
            accepted=True,
            provider_mid=provider_mid,
        )
    except Exception:
        if sent:
            from services.membership.hold_policy import hold_billing_policy
            from services.membership.reservation_reconcile import hold_failed_capture_after_send

            hold_failed_capture_after_send(
                tenant_id=tenant_id,
                reservation_id=leftover_rid,
                operation_id=leftover_rid or brain_mid or inbound_mid,
                billing_policy=hold_billing_policy(leftover_reservation_id=leftover_rid),
                provider_message_id=provider_mid,
                channel="tiktok",
            )
        else:
            release_leftover_reply(tenant_id, leftover_rid)
            _settle_tiktok_dm_send(
                tenant_id=tenant_id,
                snapshot=snapshot,
                leftover_rid=leftover_rid,
                brain_mid=brain_mid,
                accepted=False,
            )
        raise


def _settle_tiktok_dm_send(
    *,
    tenant_id: str,
    snapshot: dict[str, Any],
    leftover_rid: str | None,
    brain_mid: str,
    accepted: bool,
    provider_mid: str = "",
) -> None:
    inbound_mid = str(snapshot.get("provider_message_id") or snapshot.get("conversation_id") or "")
    from services.customer_ai.billing import settle_after_send

    settle_after_send(
        tenant_id=tenant_id,
        operation_id=brain_mid or inbound_mid,
        accepted=accepted,
        channel="tiktok",
        provider_message_id=provider_mid,
        extra_ids=(
            inbound_mid,
            leftover_rid or f"tiktok:{inbound_mid}",
            str(snapshot.get("conversation_id") or ""),
            brain_mid,
        ),
    )


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
