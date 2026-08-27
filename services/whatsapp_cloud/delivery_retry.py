"""Retry WhatsApp outbound intents that failed with retryable Graph errors."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select

from db.models.whatsapp_cloud import WhatsAppOutboundIntent
from db.session import whatsapp_session
from services.whatsapp_cloud.graph_client import WhatsAppGraphError, send_text_message
from services.whatsapp_cloud.observability import emit_wa_event
from services.whatsapp_cloud.outbound_finalization import finalize_ai_outbound_sent
from services.whatsapp_cloud.repository import WhatsAppCloudRepository

SENDING_RECONCILIATION_TIMEOUT = timedelta(minutes=5)


async def send_canonical_intent(intent_id: str) -> dict[str, Any]:
    with whatsapp_session(require=True) as session:
        intent = session.scalar(
            select(WhatsAppOutboundIntent).where(WhatsAppOutboundIntent.id == intent_id).with_for_update()
        )
        if intent is None:
            return {"ok": False, "reason": "missing_intent"}
        if intent.dispatch_state == "sent":
            return {"ok": True, "skipped": True, "reason": "already_sent"}
        if intent.dispatch_state in {"sending", "suppressed", "reconciliation_required"}:
            return {"ok": True, "skipped": True, "reason": f"already_{intent.dispatch_state}"}
        text = str(getattr(intent, "canonical_text", "") or "")
        if not text:
            return {"ok": False, "reason": "missing_canonical_text"}
        repo = WhatsAppCloudRepository(session)
        conn = repo.get_tenant_connection(tenant_id=intent.tenant_id, connection_id=intent.connection_id)
        if conn is None:
            return {"ok": False, "reason": "missing_connection"}
        conv = repo.get_tenant_conversation(tenant_id=intent.tenant_id, conversation_id=intent.conversation_id)
        if conv is None:
            return {"ok": False, "reason": "missing_conversation"}

        current_epoch = int(conv.control_epoch)
        if conv.control_state != "AI_ACTIVE" or current_epoch != int(intent.control_epoch_at_create):
            repo.update_outbound_intent(
                intent,
                dispatch_state="suppressed",
                control_epoch_at_send=current_epoch,
                error_code="epoch_race",
                error_detail=(
                    "conversation_not_ai_active" if conv.control_state != "AI_ACTIVE" else "control_epoch_changed"
                ),
            )
            emit_wa_event("ai_suppression_race", conversation_id=intent.conversation_id)
            return {"ok": True, "skipped": True, "reason": "stale_control_state"}

        try:
            token = repo.load_access_token(conn)
        except PermissionError:
            repo.update_outbound_intent(
                intent,
                dispatch_state="failed",
                error_code="credential_unavailable",
                error_detail=None,
            )
            return {"ok": False, "retryable": False, "reason": "credential_unavailable"}
        to_wa_id = conv.customer_wa_id
        phone_number_id = conn.phone_number_id
        intent.dispatch_state = "sending"
        intent.control_epoch_at_send = current_epoch
        intent.attempt_count = int(getattr(intent, "attempt_count", 0) or 0) + 1
        session.commit()
    try:
        result = await send_text_message(
            access_token=token,
            phone_number_id=phone_number_id,
            to_wa_id=to_wa_id,
            text=text,
        )
    except WhatsAppGraphError as exc:
        ambiguous = exc.retryable and exc.http_status in {None, 408, 504}
        with whatsapp_session(require=True) as session:
            intent = session.get(WhatsAppOutboundIntent, intent_id)
            if intent is not None:
                intent.dispatch_state = "reconciliation_required" if ambiguous else "failed"
                intent.error_code = exc.code
                intent.error_detail = (exc.message or "")[:255]
                session.commit()
        return {"ok": False, "retryable": exc.retryable and not ambiguous, "code": exc.code}
    except Exception as exc:
        with whatsapp_session(require=True) as session:
            intent = session.get(WhatsAppOutboundIntent, intent_id)
            if intent is not None:
                intent.dispatch_state = "reconciliation_required"
                intent.error_code = type(exc).__name__
                intent.error_detail = "ambiguous_after_submit"
                session.commit()
        return {"ok": False, "retryable": False, "reason": "ambiguous_after_submit"}
    wamid = ""
    if isinstance(result, dict):
        messages = result.get("messages") if isinstance(result.get("messages"), list) else []
        if messages and isinstance(messages[0], dict):
            wamid = str(messages[0].get("id") or "")
    try:
        with whatsapp_session(require=True) as session:
            intent = session.scalar(
                select(WhatsAppOutboundIntent).where(WhatsAppOutboundIntent.id == intent_id).with_for_update()
            )
            if intent is None:
                return {"ok": False, "reason": "missing_intent_after_send"}
            if intent.dispatch_state == "sent":
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "already_sent",
                    "wamid": intent.provider_wamid or wamid,
                }
            repo = WhatsAppCloudRepository(session)
            conv = repo.get_tenant_conversation(tenant_id=intent.tenant_id, conversation_id=intent.conversation_id)
            if conv is None:
                intent.dispatch_state = "reconciliation_required"
                intent.provider_wamid = wamid or intent.provider_wamid
                intent.error_code = "missing_conversation_after_send"
                intent.error_detail = "provider_send_succeeded_but_finalization_could_not_complete"
                return {"ok": False, "reason": "missing_conversation_after_send"}
            finalized = finalize_ai_outbound_sent(
                session,
                repo=repo,
                intent=intent,
                conversation=conv,
                canonical_text=str(intent.canonical_text or text),
                provider_wamid=wamid,
            )
        return {"ok": True, "wamid": wamid, "finalized": finalized}
    except Exception as exc:
        return _mark_post_send_finalization_for_reconciliation(
            intent_id=intent_id,
            provider_wamid=wamid,
            error=exc,
        )


def _mark_post_send_finalization_for_reconciliation(
    *,
    intent_id: str,
    provider_wamid: str,
    error: Exception,
) -> dict[str, Any]:
    """Durably prevent resend when Graph succeeded but local finalization failed."""

    with whatsapp_session(require=True) as session:
        intent = session.scalar(
            select(WhatsAppOutboundIntent).where(WhatsAppOutboundIntent.id == intent_id).with_for_update()
        )
        if intent is None:
            return {"ok": False, "retryable": False, "reason": "missing_intent_after_send"}
        # The first transaction may have committed before its context raised. Never
        # downgrade a durably sent intent in that case.
        if intent.dispatch_state == "sent":
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_sent",
                "wamid": intent.provider_wamid or provider_wamid,
            }
        intent.dispatch_state = "reconciliation_required"
        intent.provider_wamid = provider_wamid or intent.provider_wamid
        intent.error_code = "post_send_finalization_failed"
        intent.error_detail = f"provider_send_succeeded:{type(error).__name__}"[:255]

    emit_wa_event(
        "send_finalization_failed",
        intent_id=intent_id,
        error=type(error).__name__,
    )
    return {
        "ok": False,
        "retryable": False,
        "reason": "post_send_finalization_failed",
        "reconciliation_required": True,
        "wamid": provider_wamid,
    }


def _reconcile_stale_sending_intents(*, now: datetime, tenant_id: str | None = None) -> int:
    """Move abandoned provider-send claims to manual reconciliation.

    Once an intent reached ``sending``, a process crash leaves the provider
    outcome unknown.  After a conservative interval exceeding the Graph client
    timeout, the minute job durably marks it for reconciliation and never puts it
    back on the retry path.
    """

    cutoff = now - SENDING_RECONCILIATION_TIMEOUT
    with whatsapp_session(require=True) as session:
        stmt = (
            select(WhatsAppOutboundIntent)
            .where(
                WhatsAppOutboundIntent.dispatch_state == "sending",
                WhatsAppOutboundIntent.updated_at <= cutoff,
            )
            .with_for_update(skip_locked=True)
        )
        if tenant_id:
            stmt = stmt.where(WhatsAppOutboundIntent.tenant_id == tenant_id)
        stale = list(session.scalars(stmt).all())
        with_wamid = 0
        for intent in stale:
            provider_known = bool(str(intent.provider_wamid or "").strip())
            if provider_known:
                with_wamid += 1
            intent.dispatch_state = "reconciliation_required"
            intent.error_code = "stale_sending_with_wamid" if provider_known else "stale_sending_unknown_outcome"
            intent.error_detail = (
                "provider_wamid_present;finalization_unknown;never_blind_resend"
                if provider_known
                else "provider_outcome_unknown_after_worker_loss;never_blind_resend"
            )

    if stale:
        emit_wa_event(
            "stale_sending_reconciliation",
            tenant_id=tenant_id or "all",
            count=len(stale),
            provider_wamid_present=with_wamid,
        )
    return len(stale)


async def retry_pending_outbound_intents(*, tenant_id: str | None = None) -> dict[str, Any]:
    now = datetime.now(UTC)
    stale_sending_reconciled = _reconcile_stale_sending_intents(now=now, tenant_id=tenant_id)
    with whatsapp_session(require=True) as session:
        stmt = select(WhatsAppOutboundIntent).where(WhatsAppOutboundIntent.dispatch_state.in_(("failed", "pending")))
        if tenant_id:
            stmt = stmt.where(WhatsAppOutboundIntent.tenant_id == tenant_id)
        rows = list(session.scalars(stmt).all())
        ids = []
        for row in rows:
            nxt = getattr(row, "next_retry_at", None)
            if nxt is not None and nxt > now:
                continue
            ids.append(row.id)
    results = []
    for intent_id in ids:
        results.append(await send_canonical_intent(intent_id))
    return {
        "ok": True,
        "attempted": len(ids),
        "stale_sending_reconciled": stale_sending_reconciled,
        "results": results,
    }
