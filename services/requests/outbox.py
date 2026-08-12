"""Durable outbox processor for Customer Requests channel notifications."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from db.models.requests import CustomerRequest
from db.models.requests_support import CustomerRequestOutbox
from services.requests.constants import (
    EVENT_DELIVERY_BLOCKED,
    EVENT_NOTIFICATION_FAILED,
    EVENT_NOTIFICATION_SENT,
)
from services.requests.delivery import DeliveryResult, deliver_on_source_channel, redact_delivery_error
from services.requests.repository import CustomerRequestsRepository

DeliverFn = Callable[..., Awaitable[DeliveryResult]]


@dataclass(frozen=True)
class OutboxProcessResult:
    outbox_id: str
    request_id: str
    status: str
    skipped: bool = False
    error_redacted: str | None = None


def _now() -> datetime:
    return datetime.now(UTC)


def claim_pending_outbox(
    session: Session,
    *,
    tenant_id: str | None = None,
    request_id: str | None = None,
    limit: int = 20,
) -> list[CustomerRequestOutbox]:
    repo = CustomerRequestsRepository(session)
    return repo.list_pending_outbox(
        tenant_id=tenant_id,
        request_id=request_id,
        limit=limit,
    )


async def process_outbox_item(
    session: Session,
    item: CustomerRequestOutbox,
    *,
    deliver: DeliverFn | None = None,
) -> OutboxProcessResult:
    """Attempt one outbox row. Idempotent for already terminal statuses."""
    if item.status in {"sent", "blocked", "cancelled"}:
        return OutboxProcessResult(
            outbox_id=item.id,
            request_id=item.request_id,
            status=item.status,
            skipped=True,
        )

    repo = CustomerRequestsRepository(session)
    request = repo.get_for_tenant(tenant_id=item.tenant_id, request_id=item.request_id)
    if request is None:
        item.status = "failed"
        item.attempts = int(item.attempts or 0) + 1
        item.last_error = "request_not_found"
        session.flush()
        return OutboxProcessResult(
            outbox_id=item.id,
            request_id=item.request_id,
            status="failed",
            error_redacted="request_not_found",
        )

    # Hard rule: never switch away from the outbox channel or request source channel.
    if item.channel != request.source_channel:
        item.status = "failed"
        item.attempts = int(item.attempts or 0) + 1
        item.last_error = "channel_mismatch_no_switch"
        request.notification_status = "failed"
        request.last_notification_error = "channel_mismatch_no_switch"
        request.updated_at = _now()
        repo.add_event(
            tenant_id=item.tenant_id,
            request_id=item.request_id,
            event_type=EVENT_NOTIFICATION_FAILED,
            actor_kind="system",
            actor_user_id=None,
            payload={"outbox_id": item.id, "reason": "channel_mismatch_no_switch"},
        )
        session.flush()
        return OutboxProcessResult(
            outbox_id=item.id,
            request_id=item.request_id,
            status="failed",
            error_redacted="channel_mismatch_no_switch",
        )

    payload = item.payload if isinstance(item.payload, dict) else {}
    text = str(payload.get("message") or request.completion_message or "").strip()
    item.attempts = int(item.attempts or 0) + 1
    session.flush()

    deliver_fn = deliver or deliver_on_source_channel
    result = await deliver_fn(
        tenant_id=item.tenant_id,
        channel=item.channel,
        source_account_id=request.source_account_id,
        external_customer_id=request.external_customer_id,
        conversation_id=request.conversation_id,
        text=text,
        session=session,
    )
    return _apply_delivery_result(session, item, request, result)


def _apply_delivery_result(
    session: Session,
    item: CustomerRequestOutbox,
    request: CustomerRequest,
    result: DeliveryResult,
) -> OutboxProcessResult:
    repo = CustomerRequestsRepository(session)
    # Guard: delivery must report the same channel (no silent switch).
    if result.channel_used and result.channel_used != item.channel:
        item.status = "failed"
        item.last_error = "cross_channel_switch_rejected"
        request.notification_status = "failed"
        request.last_notification_error = "cross_channel_switch_rejected"
        request.updated_at = _now()
        repo.add_event(
            tenant_id=item.tenant_id,
            request_id=item.request_id,
            event_type=EVENT_NOTIFICATION_FAILED,
            actor_kind="system",
            actor_user_id=None,
            payload={
                "outbox_id": item.id,
                "reason": "cross_channel_switch_rejected",
                "attempted": result.channel_used,
            },
        )
        session.flush()
        return OutboxProcessResult(
            outbox_id=item.id,
            request_id=item.request_id,
            status="failed",
            error_redacted="cross_channel_switch_rejected",
        )

    status = result.status
    err = redact_delivery_error(result.error_redacted or "") if result.error_redacted else None
    item.status = status if status in {"sent", "failed", "blocked"} else "failed"
    item.last_error = err
    if item.status == "sent":
        item.sent_at = _now()
        request.notification_status = "sent"
        request.last_notification_error = None
        event_type = EVENT_NOTIFICATION_SENT
    elif item.status == "blocked":
        request.notification_status = "blocked"
        request.last_notification_error = err
        event_type = EVENT_DELIVERY_BLOCKED
    else:
        request.notification_status = "failed"
        request.last_notification_error = err
        event_type = EVENT_NOTIFICATION_FAILED
    request.updated_at = _now()
    repo.add_event(
        tenant_id=item.tenant_id,
        request_id=item.request_id,
        event_type=event_type,
        actor_kind="system",
        actor_user_id=None,
        payload={
            "outbox_id": item.id,
            "channel": item.channel,
            "provider_message_id": result.provider_message_id,
            "attempts": item.attempts,
            "error": err,
        },
    )
    session.flush()
    return OutboxProcessResult(
        outbox_id=item.id,
        request_id=item.request_id,
        status=item.status,
        error_redacted=err,
    )


async def process_pending_outbox(
    session: Session,
    *,
    tenant_id: str | None = None,
    request_id: str | None = None,
    limit: int = 20,
    deliver: DeliverFn | None = None,
) -> list[OutboxProcessResult]:
    items = claim_pending_outbox(session, tenant_id=tenant_id, request_id=request_id, limit=limit)
    results: list[OutboxProcessResult] = []
    for item in items:
        results.append(await process_outbox_item(session, item, deliver=deliver))
    session.commit()
    return results
