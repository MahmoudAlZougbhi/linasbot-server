"""Open customer request drafts used by FAQ guards and Luna/Tera context."""

from __future__ import annotations

from typing import Any


def list_open_collecting_drafts(
    *,
    tenant_id: str,
    customer_id: str = "",
) -> list[dict[str, Any]]:
    from db.session import WhatsAppDatabaseUnavailable, database_url, whatsapp_session
    from services.request_drafts.engine import serialize_draft
    from services.request_drafts.repository import DraftRepository

    if not tenant_id or not customer_id or not database_url():
        return []
    try:
        with whatsapp_session(require=True) as session:
            rows = DraftRepository(session).list_open(tenant_id=tenant_id, customer_id=customer_id)
            return [serialize_draft(row) for row in rows]
    except WhatsAppDatabaseUnavailable:
        return []


def list_open_drafts_for_luna(*, tenant_id: str, customer_id: str) -> list[dict[str, Any]]:
    from db.session import WhatsAppDatabaseUnavailable, database_url, whatsapp_session
    from services.request_drafts.engine import luna_draft_summary
    from services.request_drafts.repository import DraftRepository

    if not tenant_id or not customer_id or not database_url():
        return []
    try:
        with whatsapp_session(require=True) as session:
            rows = DraftRepository(session).list_open(tenant_id=tenant_id, customer_id=customer_id)
            return [luna_draft_summary(row) for row in rows]
    except WhatsAppDatabaseUnavailable:
        return []


def has_open_collecting_draft(*, tenant_id: str, customer_id: str = "") -> bool:
    return bool(list_open_collecting_drafts(tenant_id=tenant_id, customer_id=customer_id))
