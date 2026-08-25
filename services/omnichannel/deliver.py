"""Outbound delivery job: reuse canonical body, never regenerate or recharge."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox
from db.session import whatsapp_session
from services.omnichannel.classify import classify_http_delivery
from services.omnichannel.dlq import mark_dead_letter, mark_needs_owner_action
from services.omnichannel.limiter import DistributedProviderLimiter
from services.omnichannel.metrics import incr
from services.queues.handlers import PermanentJobError
from services.queues.models import QueueJob

MAX_ATTEMPTS = 8


async def handle_omnichannel_deliver(job: QueueJob) -> dict[str, Any]:
    outbox_id = str((job.payload or {}).get("outbox_id") or "").strip()
    if not outbox_id:
        raise PermanentJobError("missing outbox_id")
    with whatsapp_session(require=True) as session:
        row = session.get(OmnichannelOutboundOutbox, outbox_id)
        if row is None:
            raise PermanentJobError("outbox_missing")
        if row.state in {"delivered", "dead_letter", "needs_owner_action"}:
            return {"skipped": True, "reason": row.state}
        if row.regenerated:
            raise PermanentJobError("canonical_body_must_not_regenerate")
        row.state = "sending"
        row.attempt_count = int(row.attempt_count or 0) + 1
        session.commit()
        snapshot: dict[str, Any] = {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "channel": row.channel,
            "surface": row.surface,
            "account_id": row.account_id,
            "conversation_key": row.conversation_key,
            "canonical_body": row.canonical_body,
            "inbound_event_id": row.inbound_event_id,
            "credit_reservation_id": row.credit_reservation_id,
            "attempt_count": row.attempt_count,
            "source": row.source,
        }

    limiter = DistributedProviderLimiter()
    result = await _send(snapshot)
    channel = str(snapshot["channel"])
    account_id = str(snapshot["account_id"])
    surface = str(snapshot["surface"])
    attempt_count = int(snapshot["attempt_count"] or 0)

    decision = classify_http_delivery(
        http_status=result.get("http_status"),
        provider_code=result.get("code"),
        provider_subcode=result.get("subcode"),
        error_text=str(result.get("error") or ""),
        headers=result.get("headers") if isinstance(result.get("headers"), dict) else None,
        submitted=bool(result.get("submitted")),
        local_update_failed=bool(result.get("local_update_failed")),
        attempt=attempt_count,
        token_expired=bool(result.get("token_expired")),
        malformed_response=bool(result.get("malformed")),
        connection_reset_before_submit=bool(result.get("reset_before_submit")),
    )
    if decision.kind == "success":
        _finish_success(outbox_id, result)
        incr("delivered")
        return {"ok": True, "provider_message_id": result.get("message_id")}
    if decision.kind == "transient":
        limiter.record_throttle(
            provider=channel,
            account_id=account_id,
            endpoint=surface,
            headers=result.get("headers") if isinstance(result.get("headers"), dict) else None,
            retry_after_seconds=decision.retry_after_seconds,
            attempt=attempt_count,
        )
        _defer(outbox_id, delay=decision.retry_after_seconds, state="rate_limited", reason=decision.reason)
        incr("retry_transient")
        raise RuntimeError(f"transient:{decision.reason}")
    if decision.kind == "ambiguous":
        _mark(outbox_id, state="reconciliation_required", reason=decision.reason)
        mark_needs_owner_action(event_id=outbox_id, kind="deliver", reason=decision.reason)
        return {"ok": False, "reason": "reconciliation_required"}
    if decision.kind in {"permission_blocked", "permanent"}:
        if attempt_count >= MAX_ATTEMPTS or decision.kind == "permanent":
            _mark(outbox_id, state="dead_letter", reason=decision.reason)
            mark_dead_letter(event_id=outbox_id, kind="deliver", reason=decision.reason)
            _release_credits_if_never_submitted(snapshot, submitted=bool(result.get("submitted")))
            raise PermanentJobError(decision.reason)
        _defer(outbox_id, delay=decision.retry_after_seconds or 5.0, state="failed", reason=decision.reason)
        raise RuntimeError(decision.reason)
    _mark(outbox_id, state="needs_owner_action", reason=decision.reason)
    mark_needs_owner_action(event_id=outbox_id, kind="deliver", reason=decision.reason)
    return {"ok": False, "reason": decision.reason}


def _defer(outbox_id: str, *, delay: float, state: str, reason: str) -> None:
    with whatsapp_session(require=True) as session:
        row = session.get(OmnichannelOutboundOutbox, outbox_id)
        if row is None:
            return
        row.state = state
        row.last_error = reason[:255]
        row.next_retry_at = datetime.now(UTC) + timedelta(seconds=max(0.05, float(delay)))
        session.commit()


def _mark(outbox_id: str, *, state: str, reason: str) -> None:
    with whatsapp_session(require=True) as session:
        row = session.get(OmnichannelOutboundOutbox, outbox_id)
        if row is None:
            return
        row.state = state
        row.last_error = reason[:255]
        inbound_id = row.inbound_event_id
        session.commit()
        if inbound_id and state in {"dead_letter", "needs_owner_action"}:
            inbound = session.get(OmnichannelInboundEvent, inbound_id)
            if inbound is not None:
                inbound.state = "dead_letter" if state == "dead_letter" else inbound.state
                inbound.last_error = reason[:255]
                session.commit()


def _finish_success(outbox_id: str, result: dict[str, Any]) -> None:
    with whatsapp_session(require=True) as session:
        row = session.get(OmnichannelOutboundOutbox, outbox_id)
        if row is None:
            return
        row.state = "delivered"
        row.provider_message_id = str(result.get("message_id") or "")[:128] or None
        row.provider_request_id = str(result.get("request_id") or "")[:128] or None
        row.delivered_at = datetime.now(UTC)
        reservation = row.credit_reservation_id
        inbound_id = row.inbound_event_id
        tenant_id = row.tenant_id
        channel = row.channel
        if inbound_id:
            inbound = session.get(OmnichannelInboundEvent, inbound_id)
            if inbound is not None:
                inbound.state = "delivered"
        session.commit()
    if reservation:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.capture(
            tenant_id=tenant_id,
            reservation_id=reservation,
            provider_cost_usd=None,
            model_provider=channel,
        )


def _release_credits_if_never_submitted(snapshot: dict[str, Any], *, submitted: bool) -> None:
    reservation = snapshot.get("credit_reservation_id")
    if submitted or not reservation:
        return
    from services.credit_ledger_service import credit_ledger_service

    credit_ledger_service.release(tenant_id=str(snapshot["tenant_id"]), reservation_id=str(reservation))


async def _send(snapshot: dict[str, Any]) -> dict[str, Any]:
    channel = snapshot["channel"]
    if channel == "whatsapp":
        from services.omnichannel.channel_whatsapp import deliver_whatsapp

        return await deliver_whatsapp(snapshot)
    if channel == "tiktok":
        from services.omnichannel.channel_tiktok import deliver_tiktok

        return await deliver_tiktok(snapshot)
    if channel == "web_chat":
        from services.omnichannel.channel_web_chat import deliver_web_chat

        return await deliver_web_chat(snapshot)
    from services.omnichannel.channel_meta import deliver_meta

    return await deliver_meta(snapshot)
