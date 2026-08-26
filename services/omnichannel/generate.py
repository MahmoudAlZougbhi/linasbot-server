"""AI generation job: persist canonical reply, never send to the provider here."""

from __future__ import annotations

from typing import Any

from db.session import whatsapp_session
from services.omnichannel.accept import enqueue_deliver_job
from services.omnichannel.metrics import incr
from services.omnichannel.store import conversation_has_earlier_unfinished, persist_outbound
from services.queues.handlers import PermanentJobError
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
            raise RuntimeError("conversation_order_wait")
        row.state = "generating"
        row.attempt_count = int(row.attempt_count or 0) + 1
        session.commit()
        payload = dict(row.payload or {})
        tenant_id = row.tenant_id
        account_id = row.account_id
        conversation_key = row.conversation_key
        control_epoch = int(payload.get("control_epoch") or 0)

    text, reservation_id, skip_reason = await _generate_canonical(
        channel=channel,
        surface=surface,
        tenant_id=tenant_id,
        payload=payload,
    )
    if skip_reason:
        if reservation_id:
            from services.credit_ledger_service import credit_ledger_service

            credit_ledger_service.release(tenant_id=tenant_id, reservation_id=reservation_id)
        with whatsapp_session(require=True) as session:
            row = session.get(OmnichannelInboundEvent, inbound_id)
            if row is not None:
                row.state = "failed"
                row.last_error = skip_reason[:255]
                session.commit()
        return {"skipped": True, "reason": skip_reason}
    if not text:
        with whatsapp_session(require=True) as session:
            row = session.get(OmnichannelInboundEvent, inbound_id)
            if row is not None:
                row.state = "failed"
                row.last_error = "empty_canonical_reply"
                session.commit()
        raise RuntimeError("empty_canonical_reply")

    with whatsapp_session(require=True) as session:
        from services.omnichannel.store import operator_takeover_blocks_ai

        if operator_takeover_blocks_ai(session, conversation_key=conversation_key, control_epoch=control_epoch):
            row = session.get(OmnichannelInboundEvent, inbound_id)
            if row is not None:
                row.state = "failed"
                row.last_error = "operator_takeover"
                session.commit()
            if reservation_id:
                from services.credit_ledger_service import credit_ledger_service

                credit_ledger_service.release(tenant_id=tenant_id, reservation_id=reservation_id)
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

        return await generate_whatsapp_reply(tenant_id=tenant_id, payload=payload)
    if channel == "web_chat":
        from services.omnichannel.channel_web_chat import generate_web_chat_reply

        return await generate_web_chat_reply(tenant_id=tenant_id, payload=payload)
    if surface == "comment":
        from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

        outcome = await run_customer_reply_v2_comment(
            tenant_id=tenant_id,
            comment_text=str(payload.get("text") or payload.get("comment_text") or ""),
            channel=f"{channel}_comment",
            comments_enabled=True,
            comment_id=str(payload.get("comment_id") or payload.get("provider_event_id") or ""),
            post_id=str(payload.get("post_id") or payload.get("item_id") or ""),
            provider_sender_id=str(payload.get("author_id") or ""),
        )
        return str(getattr(outcome, "reply", None) or "").strip(), None, None
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    outcome = await run_customer_reply_v2_dm(
        tenant_id=tenant_id,
        message=str(payload.get("text") or payload.get("text_body") or ""),
        channel=channel,
        provider_sender_id=str(payload.get("sender_id") or payload.get("customer_wa_id") or ""),
    )
    if getattr(outcome, "stop", False):
        return "", None, "ai_stop"
    return str(getattr(outcome, "reply", None) or "").strip(), None, None
