"""Map outbound product messages to catalog rows for reply-to resolution (0 credits)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.products import ProductSentMessage


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def record_sent_product_message(
    session: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    channel: str,
    sent_message_id: str,
    product_id: str,
) -> None:
    message_id = str(sent_message_id or "").strip()
    if not message_id:
        return
    stmt = select(ProductSentMessage).where(
        ProductSentMessage.tenant_id == tenant_id,
        ProductSentMessage.channel == channel,
        ProductSentMessage.sent_message_id == message_id,
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        session.add(
            ProductSentMessage(
                id=_uuid(),
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                channel=channel,
                sent_message_id=message_id,
                product_id=product_id,
                created_at=_now(),
            )
        )
    else:
        row.product_id = product_id
        row.conversation_id = conversation_id
    session.flush()


def resolve_reply_to_product(
    session: Session,
    *,
    tenant_id: str,
    channel: str,
    reply_to_message_id: str,
) -> str | None:
    message_id = str(reply_to_message_id or "").strip()
    if not message_id:
        return None
    stmt = select(ProductSentMessage).where(
        ProductSentMessage.tenant_id == tenant_id,
        ProductSentMessage.channel == channel,
        ProductSentMessage.sent_message_id == message_id,
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    return str(row.product_id)


def clear_for_product(session: Session, *, tenant_id: str, product_id: str) -> None:
    stmt = select(ProductSentMessage).where(
        ProductSentMessage.tenant_id == tenant_id,
        ProductSentMessage.product_id == product_id,
    )
    for row in session.execute(stmt).scalars().all():
        session.delete(row)
    session.flush()
