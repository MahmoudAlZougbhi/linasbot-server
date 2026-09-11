"""AI generation job: persist canonical reply, never send to the provider here."""

from __future__ import annotations

from typing import Any

from db.session import whatsapp_session
from services.omnichannel.accept import enqueue_deliver_job
from services.omnichannel.metrics import incr
from services.omnichannel.store import conversation_has_earlier_unfinished, persist_outbound
from services.queues.handlers import JobNotReady, PermanentJobError
from services.queues.models import QueueJob


async def handle_omnichannel_generate(job: QueueJob) -> dict[str, Any]:
    inbound_id = str((job.payload or {}).get("inbound_id") or "").strip()
    channel = str((job.payload or {}).get("channel") or "").strip()
    surface = str((job.payload or {}).get("surface") or "").strip()
    if not inbound_id:
        raise PermanentJobError("missing inbound_id")
    from db.models.omnichannel import OmnichannelInboundEvent

    with whatsapp_session(require=True) as session:
        row = session.get(OmnichannelInboundEvent, inbound_id)
        if row is None:
            raise PermanentJobError("inbound_missing")
        if row.state == "dead_letter":
            return {"skipped": True, "reason": "dead_letter"}
        if conversation_has_earlier_unfinished(
            session,
            conversation_key=row.conversation_key,
            provider_timestamp=float(row.provider_timestamp or 0),
            inbound_id=inbound_id,
        ):
            raise JobNotReady("conversation_order_wait")
        row.state = "generating"
        row.attempt_count = int(row.attempt_count or 0) + 1
        session.commit()
        payload = dict(row.payload or {})
        event_id = str(row.provider_event_id or "").strip()
        if event_id:
            payload.setdefault("provider_event_id", event_id)
            payload.setdefault("provider_message_id", event_id)
            payload.setdefault("message_id", event_id)
        tenant_id = row.tenant_id
        account_id = row.account_id
        conversation_key = row.conversation_key
        control_epoch = int(payload.get("control_epoch") or 0)

    text, reservation_id, skip_reason = await _generate_canonical(
        channel=channel,
        surface=surface,
        tenant_id=tenant_id,
        payload=payload,
        conversation_key=conversation_key,
    )
    if skip_reason:
        from services.omnichannel.message_hold import release_unsent_omni_hold

        release_unsent_omni_hold(
            tenant_id=tenant_id,
            payload=payload,
            conversation_key=conversation_key,
            reservation_id=reservation_id,
            extra_ids=(inbound_id,),
            channel=channel,
        )
        with whatsapp_session(require=True) as session:
            row = session.get(OmnichannelInboundEvent, inbound_id)
            if row is not None:
                row.state = "failed"
                row.last_error = skip_reason[:255]
                session.commit()
        return {"skipped": True, "reason": skip_reason}
    if not text:
        from services.omnichannel.message_hold import release_unsent_omni_hold

        release_unsent_omni_hold(
            tenant_id=tenant_id,
            payload=payload,
            conversation_key=conversation_key,
            reservation_id=reservation_id,
            extra_ids=(inbound_id,),
            channel=channel,
        )
        with whatsapp_session(require=True) as session:
            row = session.get(OmnichannelInboundEvent, inbound_id)
            if row is not None:
                row.state = "failed"
                row.last_error = "empty_canonical_reply"
                session.commit()
        raise RuntimeError("empty_canonical_reply")

    try:
        with whatsapp_session(require=True) as session:
            from services.omnichannel.store import operator_takeover_blocks_ai

            if operator_takeover_blocks_ai(session, conversation_key=conversation_key, control_epoch=control_epoch):
                row = session.get(OmnichannelInboundEvent, inbound_id)
                if row is not None:
                    row.state = "failed"
                    row.last_error = "operator_takeover"
                    session.commit()
                from services.omnichannel.message_hold import release_unsent_omni_hold

                release_unsent_omni_hold(
                    tenant_id=tenant_id,
                    payload=payload,
                    conversation_key=conversation_key,
                    reservation_id=reservation_id,
                    extra_ids=(inbound_id,),
                    channel=channel,
                )
                return {"skipped": True, "reason": "operator_takeover"}
            outbox, created = persist_outbound(
                session,
                tenant_id=tenant_id,
                channel=channel,
                surface=surface,
                account_id=account_id,
                conversation_key=conversation_key,
                inbound_event_id=inbound_id,
                canonical_body=text,
                idempotency_key=f"omni:{inbound_id}:v1",
                control_epoch=control_epoch,
                credit_reservation_id=reservation_id,
                source="ai",
            )
            row = session.get(OmnichannelInboundEvent, inbound_id)
            if row is not None:
                row.state = "reply_ready"
            session.commit()
            outbox_id = outbox.id
    except Exception:
        from services.omnichannel.message_hold import release_unsent_omni_hold

        release_unsent_omni_hold(
            tenant_id=tenant_id,
            payload=payload,
            conversation_key=conversation_key,
            reservation_id=reservation_id,
            extra_ids=(inbound_id,),
            channel=channel,
        )
        raise
    incr("ai_generated")
    job_id = enqueue_deliver_job(
        outbox_id=outbox_id,
        tenant_id=tenant_id,
        channel=channel,
        surface=surface,
        conversation_key=conversation_key,
    )
    return {"ok": True, "outbox_id": outbox_id, "created": created, "deliver_job_id": job_id}


async def _generate_canonical(
    *,
    channel: str,
    surface: str,
    tenant_id: str,
    payload: dict[str, Any],
    conversation_key: str = "",
) -> tuple[str, str | None, str | None]:
    if channel == "tiktok" and surface == "dm":
        from services.omnichannel.gates import tiktok_dm_live_allowed
        from services.tiktok_business.repository import TikTokRepository

        connection = None
        connection_id = str(payload.get("connection_id") or "")
        if connection_id:
            with whatsapp_session() as session:
                connection = TikTokRepository(session).get_connection(connection_id, tenant_id=tenant_id)
        allowed, reason = tiktok_dm_live_allowed(connection)
        if not allowed:
            return "", None, reason
    if channel == "whatsapp":
        from services.omnichannel.channel_whatsapp import generate_whatsapp_reply

        return await generate_whatsapp_reply(
            tenant_id=tenant_id,
            payload=payload,
            conversation_key=conversation_key,
        )
    if channel == "web_chat":
        from services.omnichannel.channel_web_chat import generate_web_chat_reply

        return await generate_web_chat_reply(tenant_id=tenant_id, payload=payload)
    if surface == "comment":
        from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

        from services.customer_ai.history_ids import conversation_id_for_brain

        comment_id = str(payload.get("comment_id") or payload.get("provider_event_id") or "")
        post_id = str(payload.get("post_id") or payload.get("item_id") or "")
        thread = conversation_id_for_brain(payload=payload, conversation_key=conversation_key) or (
            f"comment:{tenant_id}:{channel}_comment:{post_id or comment_id or 'thread'}"
        )
        outcome = await run_customer_reply_v2_comment(
            tenant_id=tenant_id,
            comment_text=str(payload.get("text") or payload.get("comment_text") or ""),
            channel=f"{channel}_comment",
            comments_enabled=True,
            comment_id=comment_id,
            post_id=post_id,
            caption=str(payload.get("caption") or payload.get("post_preview") or ""),
            parent_comment=str(payload.get("parent_comment") or payload.get("parent_text") or ""),
            provider_sender_id=str(payload.get("author_id") or payload.get("author_user_id") or ""),
            comment_context={"conversation_id": thread, "comment_id": comment_id, "post_id": post_id},
        )
        from services.customer_ai.comments.destinations import (
            destinations_from_outcome,
            public_text_for_channel,
        )

        plan = destinations_from_outcome(outcome)
        reply = public_text_for_channel(plan, private_send_possible=False)
        if plan.public_depends_on_private and not reply:
            from services.omnichannel.message_hold import release_unsent_omni_hold

            release_unsent_omni_hold(
                tenant_id=tenant_id,
                payload=payload,
                conversation_key=conversation_key,
                extra_ids=(comment_id, post_id, thread),
                channel=f"{channel}_comment",
            )
            return "", None, "public_depends_on_unsent_private"
        if not reply:
            from services.omnichannel.message_hold import release_unsent_omni_hold

            release_unsent_omni_hold(
                tenant_id=tenant_id,
                payload=payload,
                conversation_key=conversation_key,
                extra_ids=(comment_id, post_id, thread),
                channel=f"{channel}_comment",
            )
            return "", None, str(getattr(outcome, "reason", "") or "engine_removed")
        return reply, None, None
    from services.customer_ai.history_ids import conversation_id_for_brain, message_id_for_brain
    from services.customer_ai.leftover_reserve import reserve_leftover_reply
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    sender = str(payload.get("sender_id") or payload.get("customer_wa_id") or payload.get("customer_open_id") or "")
    inbound_mid = message_id_for_brain(payload)
    leftover_rid = None
    try:
        leftover_rid = reserve_leftover_reply(
            tenant_id=tenant_id,
            request_id=f"omni:{channel}:{inbound_mid or conversation_key}",
            operation_type="omnichannel_customer_reply",
            pin_ids=(inbound_mid, conversation_key),
        )
    except PermissionError:
        return "", None, "insufficient_credits"
    try:
        from services.customer_reply_v2.inbound_media import planner_text_from_inbound

        inbound_media = payload.get("inbound_media") if isinstance(payload.get("inbound_media"), dict) else {}
        message = planner_text_from_inbound(
            inbound_media,
            text=str(payload.get("text") or payload.get("text_body") or ""),
        )
        if not message and inbound_media.get("attachment_types"):
            message = "Sent a message."
        outcome = await run_customer_reply_v2_dm(
            tenant_id=tenant_id,
            message=message,
            channel=channel,
            provider_sender_id=sender,
            user_id=sender,
            conversation_id=conversation_id_for_brain(payload=payload, conversation_key=conversation_key),
            message_id=inbound_mid,
            inbound_media=inbound_media or None,
        )
        if getattr(outcome, "stop", False) or not str(getattr(outcome, "reply", None) or "").strip():
            from services.omnichannel.message_hold import release_unsent_omni_hold

            release_unsent_omni_hold(
                tenant_id=tenant_id,
                payload=payload,
                conversation_key=conversation_key,
                reservation_id=leftover_rid,
                extra_ids=(inbound_mid,),
                channel=channel,
            )
            return "", None, str(getattr(outcome, "reason", "") or "ai_stop")
        return str(getattr(outcome, "reply", None) or "").strip(), leftover_rid, None
    except Exception:
        from services.omnichannel.message_hold import release_unsent_omni_hold

        release_unsent_omni_hold(
            tenant_id=tenant_id,
            payload=payload,
            conversation_key=conversation_key,
            reservation_id=leftover_rid,
            extra_ids=(inbound_mid,),
            channel=channel,
        )
        raise
