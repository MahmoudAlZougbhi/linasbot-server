"""PostgreSQL persist for omnichannel inbound + outbound. Redis is never SoT."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.omnichannel import OmnichannelInboundEvent, OmnichannelOutboundOutbox
from services.omnichannel.contract import INBOUND_TERMINAL, NormalizedInbound


def _now() -> datetime:
    return datetime.now(UTC)


def payload_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _inbound_identity(event: NormalizedInbound) -> tuple[Any, Any, Any, Any]:
    return (
        OmnichannelInboundEvent.tenant_id == event.tenant_id,
        OmnichannelInboundEvent.channel == event.channel,
        OmnichannelInboundEvent.surface == event.surface,
        OmnichannelInboundEvent.provider_event_id == event.provider_event_id,
    )


def persist_inbound(session: Session, event: NormalizedInbound) -> tuple[OmnichannelInboundEvent, bool]:
    existing = session.scalar(select(OmnichannelInboundEvent).where(*_inbound_identity(event)))
    if existing is not None:
        return existing, False
    identity = {
        "id": event.provider_event_id,
        "c": event.channel,
        "s": event.surface,
        "t": event.tenant_id,
    }
    row = OmnichannelInboundEvent(
        id=f"ocb_{payload_hash(identity)[:40]}",
        provider_event_id=event.provider_event_id[:128],
        tenant_id=event.tenant_id,
        account_id=event.account_id[:128],
        channel=event.channel,
        surface=event.surface,
        conversation_key=event.conversation_key[:255],
        provider_timestamp=float(event.provider_timestamp or time.time()),
        payload_hash=event.payload_hash or payload_hash(event.payload),
        state="accepted",
        payload=dict(event.payload),
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        existing = session.scalar(select(OmnichannelInboundEvent).where(*_inbound_identity(event)))
        if existing is None:
            raise
        return existing, False
    return row, True


def persist_outbound(
    session: Session,
    *,
    tenant_id: str,
    channel: str,
    surface: str,
    account_id: str,
    conversation_key: str,
    inbound_event_id: str | None,
    canonical_body: str,
    idempotency_key: str,
    control_epoch: int = 0,
    credit_reservation_id: str | None = None,
    source: str = "ai",
) -> tuple[OmnichannelOutboundOutbox, bool]:
    existing = session.scalar(
        select(OmnichannelOutboundOutbox).where(OmnichannelOutboundOutbox.idempotency_key == idempotency_key)
    )
    if existing is not None:
        return existing, False
    row = OmnichannelOutboundOutbox(
        tenant_id=tenant_id,
        channel=channel,
        surface=surface,
        account_id=account_id[:128],
        conversation_key=conversation_key[:255],
        inbound_event_id=inbound_event_id,
        canonical_body=canonical_body,
        idempotency_key=idempotency_key[:191],
        control_epoch=int(control_epoch),
        credit_reservation_id=credit_reservation_id,
        source=source[:16],
        state="queued",
    )
    try:
        with session.begin_nested():
            session.add(row)
            session.flush()
    except IntegrityError:
        existing = session.scalar(
            select(OmnichannelOutboundOutbox).where(OmnichannelOutboundOutbox.idempotency_key == idempotency_key)
        )
        if existing is None:
            raise
        return existing, False
    return row, True


def list_unfinished_inbound(session: Session, *, older_than_seconds: float = 30.0) -> list[OmnichannelInboundEvent]:
    cutoff_ts = _now().timestamp() - older_than_seconds
    rows = session.scalars(
        select(OmnichannelInboundEvent).where(OmnichannelInboundEvent.state.notin_(tuple(INBOUND_TERMINAL)))
    ).all()
    out: list[OmnichannelInboundEvent] = []
    for row in rows:
        if dict(row.payload or {}).get("_mirror_only"):
            continue
        if older_than_seconds > 0:
            raw = row.updated_at
            if raw is not None and raw.tzinfo is None:
                raw = raw.replace(tzinfo=UTC)
            updated = raw.timestamp() if raw else 0.0
            if updated > cutoff_ts:
                continue
        out.append(row)
    return out


def conversation_has_earlier_unfinished(
    session: Session, *, conversation_key: str, provider_timestamp: float, inbound_id: str
) -> bool:
    found = session.scalar(
        select(OmnichannelInboundEvent.id)
        .where(
            OmnichannelInboundEvent.conversation_key == conversation_key,
            OmnichannelInboundEvent.id != inbound_id,
            OmnichannelInboundEvent.provider_timestamp < float(provider_timestamp),
            OmnichannelInboundEvent.state.notin_(tuple(INBOUND_TERMINAL)),
        )
        .limit(1)
    )
    return found is not None


def operator_takeover_blocks_ai(session: Session, *, conversation_key: str, control_epoch: int) -> bool:
    epoch = session.scalar(
        select(func.max(OmnichannelOutboundOutbox.control_epoch)).where(
            OmnichannelOutboundOutbox.conversation_key == conversation_key,
            OmnichannelOutboundOutbox.source == "operator",
            OmnichannelOutboundOutbox.state != "dead_letter",
        )
    )
    return int(epoch or 0) > int(control_epoch)


def list_retryable_outbound(session: Session) -> list[OmnichannelOutboundOutbox]:
    now = _now()
    rows = session.scalars(
        select(OmnichannelOutboundOutbox).where(
            OmnichannelOutboundOutbox.state.in_(("queued", "rate_limited", "failed"))
        )
    ).all()
    ready: list[OmnichannelOutboundOutbox] = []
    for row in rows:
        if row.next_retry_at is not None and row.next_retry_at > now:
            continue
        ready.append(row)
    return ready


def backlog_snapshot(session: Session) -> dict[str, Any]:
    inbound_rows = session.execute(
        select(OmnichannelInboundEvent.state, func.count()).group_by(OmnichannelInboundEvent.state)
    ).all()
    outbound_rows = session.execute(
        select(OmnichannelOutboundOutbox.state, func.count()).group_by(OmnichannelOutboundOutbox.state)
    ).all()
    inbound: dict[str, int] = {str(k): int(v) for k, v in inbound_rows}
    outbound: dict[str, int] = {str(k): int(v) for k, v in outbound_rows}
    return {"inbound": inbound, "outbound": outbound}


accept_inbound = persist_inbound
