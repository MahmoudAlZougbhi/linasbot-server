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


def _message_settle_ops(*, inbound: Any, inbound_id: str, reservation: str = "") -> tuple[str, tuple[str, ...]]:
    provider = str(getattr(inbound, "provider_event_id", "") or "")
    payload = dict(getattr(inbound, "payload", None) or {})
    if provider:
        payload.setdefault("provider_event_id", provider)
        payload.setdefault("provider_message_id", provider)
        payload.setdefault("message_id", provider)
    from services.customer_ai.history_ids import message_id_for_brain

    brain_mid = message_id_for_brain(payload)
    primary = brain_mid or provider or inbound_id
    extras = tuple(item for item in (inbound_id, reservation, provider, brain_mid) if item)
    return primary, extras


def _limiter_provider(channel: str) -> str:
    ch = (channel or "").strip().lower()
    if ch in {"instagram", "facebook", "whatsapp"}:
        return "meta"
    if ch == "tiktok":
        return "tiktok"
    return "openai"


async def handle_omnichannel_deliver(job: QueueJob) -> dict[str, Any]:
    outbox_id = str((job.payload or {}).get("outbox_id") or "").strip()
    if not outbox_id:
        raise PermanentJobError("missing outbox_id")
    with whatsapp_session(require=True) as session:
        row = session.get(OmnichannelOutboundOutbox, outbox_id)
        if row is None:
            raise PermanentJobError("outbox_missing")
        if row.state in {"delivered", "dead_letter", "needs_owner_action", "reconciliation_required"}:
            return {"skipped": True, "reason": row.state}
        if row.regenerated:
            raise PermanentJobError("canonical_body_must_not_regenerate")
        row.state = "sending"
        row.attempt_count = int(row.attempt_count or 0) + 1
        session.commit()
        inbound = session.get(OmnichannelInboundEvent, row.inbound_event_id) if row.inbound_event_id else None
        primary, extras = _message_settle_ops(
            inbound=inbound,
            inbound_id=str(row.inbound_event_id or ""),
            reservation=str(row.credit_reservation_id or ""),
        )
        snapshot: dict[str, Any] = {
            "id": row.id,
            "tenant_id": row.tenant_id,
            "channel": row.channel,
            "surface": row.surface,
            "account_id": row.account_id,
            "conversation_key": row.conversation_key,
            "canonical_body": row.canonical_body,
            "inbound_event_id": row.inbound_event_id,
            "message_operation_id": primary,
            "message_extra_ids": extras,
            "credit_reservation_id": row.credit_reservation_id,
            "attempt_count": row.attempt_count,
            "source": row.source,
            "control_epoch": int(row.control_epoch or 0),
        }

    channel = str(snapshot["channel"])
    account_id = str(snapshot["account_id"])
    surface = str(snapshot["surface"])
    attempt_count = int(snapshot["attempt_count"] or 0)
    tenant_id = str(snapshot["tenant_id"])
    if snapshot.get("source") == "ai":
        from services.omnichannel.store import operator_takeover_blocks_ai

        with whatsapp_session(require=True) as session:
            if operator_takeover_blocks_ai(
                session,
                conversation_key=str(snapshot["conversation_key"]),
                control_epoch=int(snapshot.get("control_epoch") or 0),
            ):
                _mark(outbox_id, state="needs_owner_action", reason="operator_takeover")
                _release_credits_if_never_submitted(snapshot, submitted=False)
                return {"ok": False, "reason": "operator_takeover"}

    limiter = DistributedProviderLimiter()
    provider = _limiter_provider(channel)
    entered = False
    try:
        gate = limiter.try_enter(
            provider=provider,
            tenant_id=tenant_id,
            account_id=account_id,
            endpoint=surface,
        )
        if not gate.allowed:
            _defer(
                outbox_id,
                delay=gate.retry_after_seconds,
                state="rate_limited",
                reason=gate.reason,
            )
            incr("retry_transient")
            raise RuntimeError(f"limiter:{gate.reason}")
        entered = True
        result = await _send(snapshot)
    finally:
        if entered:
            limiter.exit(provider=provider, tenant_id=tenant_id)

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
        try:
            _finish_success(outbox_id, result)
        except Exception:
            _mark(outbox_id, state="reconciliation_required", reason="accepted_local_state_update_failed")
            mark_needs_owner_action(event_id=outbox_id, kind="deliver", reason="accepted_local_state_update_failed")
            return {"ok": False, "reason": "reconciliation_required"}
        incr("delivered")
        return {"ok": True, "provider_message_id": result.get("message_id")}
    if decision.kind == "transient":
        limiter.record_throttle(
            provider=provider,
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
        inbound = session.get(OmnichannelInboundEvent, inbound_id) if inbound_id else None
        if inbound is not None:
            inbound.state = "delivered"
        operation_id, extra_ids = _message_settle_ops(
            inbound=inbound,
            inbound_id=str(inbound_id or ""),
            reservation=str(reservation or ""),
        )
        session.commit()
    if reservation:
        from services.membership.message_flags import message_billing_enabled

        if not message_billing_enabled():
            from services.customer_ai.leftover_reserve import capture_leftover_reply

            capture_leftover_reply(
                tenant_id,
                reservation,
                model_provider=channel,
                provider_message_id=str(result.get("message_id") or ""),
            )
    from services.customer_ai.billing import settle_after_send

    settle_after_send(
        tenant_id=tenant_id,
        operation_id=operation_id,
        accepted=True,
        channel=channel,
        provider_message_id=str(result.get("message_id") or ""),
        extra_ids=extra_ids,
    )


def _release_credits_if_never_submitted(snapshot: dict[str, Any], *, submitted: bool) -> None:
    reservation = snapshot.get("credit_reservation_id")
    inbound_id = str(snapshot.get("inbound_event_id") or "")
    tenant_id = str(snapshot.get("tenant_id") or "")
    if submitted or not tenant_id:
        return
    from services.membership.message_flags import message_billing_enabled

    if message_billing_enabled():
        from services.customer_ai.billing import settle_after_send

        settle_after_send(
            tenant_id=tenant_id,
            operation_id=str(snapshot.get("message_operation_id") or inbound_id or reservation or ""),
            accepted=False,
            channel=str(snapshot.get("channel") or ""),
            extra_ids=tuple(snapshot.get("message_extra_ids") or ()) or (inbound_id, str(reservation or "")),
        )
        return
    if not reservation:
        return
    from services.customer_ai.leftover_reserve import release_leftover_reply

    release_leftover_reply(tenant_id, str(reservation))


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
