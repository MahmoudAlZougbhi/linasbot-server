"""Owner-controlled hide flag. It changes no tenant data and never covers a protected tenant."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text

_SQL = """
CREATE TABLE IF NOT EXISTS owner_portal_tenant_visibility (
    tenant_id TEXT PRIMARY KEY,
    hidden INTEGER NOT NULL,
    updated_at TEXT NOT NULL DEFAULT ''
)
"""


def hidden_override(tenant_id: str) -> bool | None:
    from db.session import whatsapp_session

    tid = (tenant_id or "").strip().lower()
    if not tid:
        return None
    try:
        with whatsapp_session(require=False) as session:
            if session is None:
                return None
            row = session.execute(
                text("SELECT hidden FROM owner_portal_tenant_visibility WHERE tenant_id = :id"),
                {"id": tid},
            ).first()
    except Exception:
        return None
    if row is None:
        return None
    return bool(int(row[0] or 0))


def set_hidden(tenant_id: str, hidden: bool) -> str:
    from db.session import whatsapp_session
    from services.team.tenant_identity import PROTECTED_TENANTS

    tid = (tenant_id or "").strip().lower()
    if tid in PROTECTED_TENANTS:
        return "protected"
    try:
        with whatsapp_session(require=False) as session:
            if session is None:
                return "unavailable"
            session.execute(text(_SQL))
            session.execute(
                text(
                    """
                    INSERT INTO owner_portal_tenant_visibility (tenant_id, hidden, updated_at)
                    VALUES (:id, :hidden, :updated)
                    ON CONFLICT (tenant_id) DO UPDATE
                    SET hidden = excluded.hidden, updated_at = excluded.updated_at
                    """
                ),
                {"id": tid, "hidden": 1 if hidden else 0, "updated": datetime.now(UTC).isoformat()},
            )
    except Exception:
        return "unavailable"
    return "ok"
