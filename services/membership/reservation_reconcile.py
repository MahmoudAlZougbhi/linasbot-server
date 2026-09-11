"""Bounded reservation reconciliation for leftover credits and message units."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from services.membership.pending_settlement import (
    PendingSettlement,
    bump_attempt,
    list_pending,
    pending_counts,
    record_pending_after_send,
    upsert,
)

DEFAULT_BATCH = 50
ACTIVE_MAX_AGE_SECONDS = 3600


def _age_seconds(stamp: str) -> float:
    if not stamp:
        return 0.0
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return max(0.0, (datetime.now(timezone.utc) - parsed).total_seconds())


def _retry_legacy(item: PendingSettlement) -> str:
    from services.credit_ledger_service import credit_ledger_service

    if item.send_status != "sent":
        if _age_seconds(item.created_at) < ACTIVE_MAX_AGE_SECONDS:
            return "active"
        upsert(
            tenant_id=item.tenant_id,
            reservation_id=item.reservation_id,
            operation_id=item.operation_id,
            billing_policy="legacy_credits",
            state="unresolved",
            reason="stale_reserved_no_send_receipt",
            send_status=item.send_status,
            provider_message_id=item.provider_message_id,
            channel=item.channel,
        )
        return "unresolved"
    try:
        credit_ledger_service.capture(
            tenant_id=item.tenant_id,
            reservation_id=item.reservation_id,
            provider_cost_usd=None,
            model_provider=item.channel or "reconcile",
        )
        from services.customer_ai.leftover_reserve import complete_leftover_capture

        complete_leftover_capture(
            item.tenant_id,
            item.reservation_id,
            operation_id=item.operation_id,
            provider_message_id=item.provider_message_id,
            extra_ids=_item_candidates(item),
        )
        return "settled"
    except Exception as exc:
        updated = bump_attempt(item.settlement_id, reason=type(exc).__name__)
        return "unresolved" if updated and updated.state == "unresolved" else "retry"


def _item_candidates(item: PendingSettlement) -> list[str]:
    raw = item.extra.get("candidate_ids") or item.extra.get("aliases") or []
    seen: list[str] = []
    for value in (item.operation_id, item.reservation_id, item.provider_message_id, *raw):
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    return seen


def _retry_message(item: PendingSettlement) -> str:
    from services.membership.message_ledger import settle

    if item.send_status != "sent":
        if _age_seconds(item.created_at) < ACTIVE_MAX_AGE_SECONDS:
            return "active"
        upsert(
            tenant_id=item.tenant_id,
            reservation_id=item.reservation_id,
            operation_id=item.operation_id,
            billing_policy="message_units",
            state="unresolved",
            reason="stale_reserved_no_send_receipt",
        )
        return "unresolved"
    settled_op = ""
    last_error = ""
    for op in _item_candidates(item):
        try:
            settle(tenant_id=item.tenant_id, operation_id=op, accepted=True)
            settled_op = op
            break
        except KeyError:
            continue
        except Exception as exc:
            last_error = type(exc).__name__
            break
    if not settled_op:
        updated = bump_attempt(item.settlement_id, reason=last_error or "missing_reservation")
        return "unresolved" if updated and updated.state == "unresolved" else "retry"
    upsert(
        tenant_id=item.tenant_id,
        reservation_id=item.reservation_id,
        operation_id=settled_op,
        billing_policy="message_units",
        state="settled",
        send_status="sent",
        provider_message_id=item.provider_message_id,
        channel=item.channel,
        reason="reconcile_settle",
        extra={"candidate_ids": _item_candidates(item)},
    )
    from services.customer_ai.outbox import acknowledge_sent

    acknowledge_sent(
        tenant_id=item.tenant_id,
        operation_id=settled_op,
        provider_message_id=item.provider_message_id,
        extra_ids=_item_candidates(item),
    )
    return "settled"


def watch_stale_message_reservations(
    *,
    limit: int = DEFAULT_BATCH,
    max_age_seconds: int = ACTIVE_MAX_AGE_SECONDS,
) -> int:
    from datetime import datetime, timedelta, timezone

    from services.membership.message_ledger import list_stale_reserved

    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(1, int(max_age_seconds)))
    watched = 0
    for reservation in list_stale_reserved(older_than=cutoff, limit=limit):
        upsert(
            tenant_id=reservation.tenant_id,
            reservation_id=reservation.reservation_id,
            operation_id=reservation.operation_id,
            billing_policy="message_units",
            state="unresolved",
            reason="stale_message_reservation_no_receipt",
        )
        watched += 1
    return watched


def watch_stale_legacy_credits(*, limit: int = DEFAULT_BATCH, max_age_seconds: int = ACTIVE_MAX_AGE_SECONDS) -> int:
    from services.membership.credit_reservation_index import list_stale_open, seed_from_pending_settlements
    from services.membership.credit_reservation_scan import seed_from_known_ledgers
    from services.membership.pending_settlement import get_pending

    seed_from_pending_settlements(limit=limit)
    seed_from_known_ledgers(limit=limit)

    watched = 0
    for item in list_stale_open(older_than_seconds=max_age_seconds, limit=limit):
        existing = get_pending(item.tenant_id, item.reservation_id, item.request_id)
        if existing and (
            existing.send_status == "sent"
            or existing.state in {"pending_settlement", "settled", "released"}
        ):
            continue
        upsert(
            tenant_id=item.tenant_id,
            reservation_id=item.reservation_id,
            operation_id=item.request_id or item.reservation_id,
            billing_policy="legacy_credits",
            state="unresolved",
            reason="stale_credit_reservation_no_receipt",
        )
        watched += 1
    return watched


def run_reservation_reconcile(*, limit: int = DEFAULT_BATCH, after_id: str = "") -> dict[str, Any]:
    """Retry pending captures. Never release a confirmed send. Never scan guessed tenants."""
    watch_stale_message_reservations(limit=limit)
    watch_stale_legacy_credits(limit=limit)
    batch = list_pending(limit=limit, after_id=after_id)
    tallies = {"settled": 0, "released": 0, "unresolved": 0, "retry": 0, "active": 0, "examined": 0}
    last_id = after_id
    for item in batch:
        tallies["examined"] += 1
        last_id = item.settlement_id
        if item.billing_policy == "legacy_credits":
            outcome = _retry_legacy(item)
        else:
            outcome = _retry_message(item)
        tallies[outcome] = tallies.get(outcome, 0) + 1
    counts = pending_counts()
    from services.customer_ai.outbox import outbox_counts

    return {
        "ran": True,
        "examined": tallies["examined"],
        "settled": tallies["settled"],
        "released": tallies["released"],
        "unresolved": counts.get("unresolved", 0),
        "retry": tallies["retry"],
        "active": tallies["active"],
        "next_after_id": last_id,
        "pending_settlement": counts.get("pending_settlement", 0),
        "outbox": outbox_counts(),
        "note": "Confirmed sends stay reserved until capture/settle succeeds. Unknown outcomes are unresolved. Accepted outbox envelopes are not regenerated or auto-resent.",
    }


def hold_failed_capture_after_send(
    *,
    tenant_id: str,
    reservation_id: str | None,
    operation_id: str,
    billing_policy: str,
    provider_message_id: str = "",
    channel: str = "",
) -> None:
    if not tenant_id or not (reservation_id or operation_id):
        return
    record_pending_after_send(
        tenant_id=tenant_id,
        reservation_id=reservation_id or operation_id,
        operation_id=operation_id or (reservation_id or ""),
        billing_policy="legacy_credits" if billing_policy == "legacy_credits" else "message_units",
        provider_message_id=provider_message_id,
        channel=channel,
    )
    upsert(
        tenant_id=tenant_id,
        reservation_id=reservation_id or operation_id,
        operation_id=operation_id or (reservation_id or ""),
        billing_policy="legacy_credits" if billing_policy == "legacy_credits" else "message_units",
        state="pending_settlement",
        send_status="sent",
        provider_message_id=provider_message_id,
        channel=channel,
        reason="capture_failed_after_send",
        extra={
            "candidate_ids": [
                item
                for item in (operation_id, reservation_id, provider_message_id)
                if str(item or "").strip()
            ]
        },
    )
    from services.customer_ai.outbox import acknowledge_pending_settlement

    acknowledge_pending_settlement(
        tenant_id=tenant_id,
        operation_id=operation_id or (reservation_id or ""),
        provider_message_id=provider_message_id,
        extra_ids=(reservation_id or "",),
    )
