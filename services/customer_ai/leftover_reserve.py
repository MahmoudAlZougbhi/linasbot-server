"""Leftover-credit reserve while message billing is off. No 1 credit = 1 message."""

from __future__ import annotations

_PINS: dict[str, str] = {}


def reset_leftover_pins_for_tests() -> None:
    _PINS.clear()
    from services.membership.credit_reservation_index import reset_credit_reservation_index_for_tests

    reset_credit_reservation_index_for_tests()


def leftover_policy_for(tenant_id: str, *operation_ids: str) -> str | None:
    from services.membership.pending_settlement import _sql_ready, policy_for_operation

    stored = policy_for_operation(tenant_id, *operation_ids)
    if stored:
        return stored
    if _sql_ready():
        _unpin(tenant_id, *operation_ids)
        return None
    for item in operation_ids:
        text = str(item or "").strip()
        if not text:
            continue
        found = _PINS.get(f"{tenant_id}:{text}")
        if found:
            return found
    return None


def _pin(tenant_id: str, *operation_ids: str) -> None:
    for item in operation_ids:
        text = str(item or "").strip()
        if text:
            _PINS[f"{tenant_id}:{text}"] = "legacy_credits"


def _unpin(tenant_id: str, *operation_ids: str) -> None:
    for item in operation_ids:
        text = str(item or "").strip()
        if text:
            _PINS.pop(f"{tenant_id}:{text}", None)


def reserve_leftover_reply(
    *,
    tenant_id: str,
    request_id: str,
    operation_type: str,
    pin_ids: tuple[str, ...] | list[str] = (),
) -> str | None:
    from services.membership.message_flags import message_billing_enabled

    if message_billing_enabled() or not tenant_id or not request_id:
        return None
    from services.credit_ledger_service import credit_ledger_service

    reservation_id = credit_ledger_service.reserve(
        tenant_id=tenant_id,
        user_id=None,
        credits=1,
        operation_type=operation_type,
        request_id=request_id,
    )
    remember_leftover_hold(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        request_id=request_id,
        operation_type=operation_type,
        pin_ids=pin_ids,
    )
    return reservation_id


def remember_leftover_hold(
    *,
    tenant_id: str,
    reservation_id: str,
    request_id: str,
    operation_type: str,
    pin_ids: tuple[str, ...] | list[str] = (),
) -> None:
    """Index an already-reserved leftover hold. Does not reserve again."""
    from services.membership.pending_settlement import record_hold

    aliases: list[str] = []
    for item in (request_id, reservation_id, *pin_ids):
        text = str(item or "").strip()
        if text and text not in aliases:
            aliases.append(text)
    record_hold(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        operation_id=request_id,
        billing_policy="legacy_credits",
        channel=operation_type,
        extra={"operation_type": operation_type, "candidate_ids": aliases},
    )
    _pin(tenant_id, request_id, reservation_id, *pin_ids)
    from services.membership.credit_reservation_index import record_open

    record_open(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        request_id=request_id,
        operation_type=operation_type,
    )


def complete_leftover_release(
    tenant_id: str,
    reservation_id: str,
    *,
    extra_ids: tuple[str, ...] | list[str] = (),
) -> None:
    """Release leftover metadata after a successful credit release. Does not release again."""
    from services.membership.pending_settlement import get_pending, upsert

    extra_op = next((str(item or "").strip() for item in extra_ids if str(item or "").strip()), "")
    held = None
    try:
        held = get_pending(tenant_id, reservation_id, extra_op)
    except Exception:
        held = None
    aliases = [reservation_id, extra_op, *[str(item or "") for item in extra_ids]]
    if held is not None:
        aliases.append(held.operation_id)
        aliases.extend(str(item or "") for item in (held.extra.get("candidate_ids") or []))
    _unpin(tenant_id, *aliases)
    upsert(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        operation_id=held.operation_id if held is not None else reservation_id,
        billing_policy="legacy_credits",
        state="released",
        reason="unused_or_failed_before_send",
    )
    from services.membership.credit_reservation_index import mark_closed

    mark_closed(reservation_id, state="released")


def release_leftover_reply(tenant_id: str, reservation_id: str | None) -> None:
    if not tenant_id or not reservation_id:
        return
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.release(tenant_id=tenant_id, reservation_id=reservation_id)
        complete_leftover_release(tenant_id, reservation_id)
    except Exception:
        return


def complete_leftover_capture(
    tenant_id: str,
    reservation_id: str,
    *,
    operation_id: str = "",
    provider_message_id: str = "",
    extra_ids: tuple[str, ...] | list[str] = (),
) -> None:
    """Settle leftover metadata after a successful credit capture. Does not capture again."""
    from services.membership.pending_settlement import get_pending, upsert

    op = operation_id or reservation_id
    held = None
    try:
        held = get_pending(tenant_id, reservation_id, op)
    except Exception:
        held = None
    aliases = [reservation_id, op, *[str(item or "") for item in extra_ids]]
    if held is not None:
        aliases.append(held.operation_id)
        aliases.extend(str(item or "") for item in (held.extra.get("candidate_ids") or []))
    _unpin(tenant_id, *aliases)
    upsert(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        operation_id=held.operation_id if held is not None else op,
        billing_policy="legacy_credits",
        state="settled",
        send_status="sent",
        provider_message_id=provider_message_id,
        reason="capture",
    )
    from services.membership.credit_reservation_index import mark_closed

    mark_closed(reservation_id, state="settled")
    from services.customer_ai.outbox import acknowledge_sent

    acknowledge_sent(
        tenant_id=tenant_id,
        operation_id=held.operation_id if held is not None else op,
        provider_message_id=provider_message_id,
        extra_ids=(reservation_id, op, *[str(item or "") for item in extra_ids]),
    )


def capture_leftover_reply(
    tenant_id: str,
    reservation_id: str | None,
    *,
    model_provider: str,
    operation_id: str = "",
    provider_message_id: str = "",
) -> bool:
    if not tenant_id or not reservation_id:
        return False
    op = operation_id or reservation_id
    try:
        from services.credit_ledger_service import credit_ledger_service

        credit_ledger_service.capture(
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            provider_cost_usd=None,
            model_provider=model_provider,
        )
        complete_leftover_capture(
            tenant_id,
            reservation_id,
            operation_id=op,
            provider_message_id=provider_message_id,
        )
        return True
    except Exception:
        from services.membership.reservation_reconcile import hold_failed_capture_after_send

        hold_failed_capture_after_send(
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            operation_id=op,
            billing_policy="legacy_credits",
            provider_message_id=provider_message_id,
            channel=model_provider,
        )
        from services.membership.credit_reservation_index import mark_closed

        mark_closed(reservation_id, state="pending_settlement")
        return False
