"""Per-conversation active product context for follow-up questions."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from db.models.products import ProductConversationContext

CONTEXT_SOURCES = frozenset(
    {"title_search", "luna_title_match", "image_match", "url_match", "reply_to_product", "manual"}
)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(UTC)


def get_active_product(
    session: Session,
    *,
    tenant_id: str,
    conversation_id: str,
) -> dict[str, Any] | None:
    stmt = select(ProductConversationContext).where(
        ProductConversationContext.tenant_id == tenant_id,
        ProductConversationContext.conversation_id == conversation_id,
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        return None
    return {
        "active_product_id": row.active_product_id,
        "source": row.source,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def set_active_product(
    session: Session,
    *,
    tenant_id: str,
    conversation_id: str,
    product_id: str,
    source: str,
) -> dict[str, Any]:
    normalized_source = source if source in CONTEXT_SOURCES else "manual"
    stmt = select(ProductConversationContext).where(
        ProductConversationContext.tenant_id == tenant_id,
        ProductConversationContext.conversation_id == conversation_id,
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is None:
        row = ProductConversationContext(
            id=_uuid(),
            tenant_id=tenant_id,
            conversation_id=conversation_id,
            active_product_id=product_id,
            source=normalized_source,
            updated_at=_now(),
        )
        session.add(row)
    else:
        row.active_product_id = product_id
        row.source = normalized_source
        row.updated_at = _now()
    session.flush()
    return {
        "active_product_id": row.active_product_id,
        "source": row.source,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def clear_active_product(session: Session, *, tenant_id: str, conversation_id: str) -> None:
    stmt = select(ProductConversationContext).where(
        ProductConversationContext.tenant_id == tenant_id,
        ProductConversationContext.conversation_id == conversation_id,
    )
    row = session.execute(stmt).scalar_one_or_none()
    if row is not None:
        session.delete(row)
        session.flush()


def clear_for_product(session: Session, *, tenant_id: str, product_id: str) -> None:
    stmt = select(ProductConversationContext).where(
        ProductConversationContext.tenant_id == tenant_id,
        ProductConversationContext.active_product_id == product_id,
    )
    for row in session.execute(stmt).scalars().all():
        session.delete(row)
    session.flush()
