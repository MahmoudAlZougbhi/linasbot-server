"""Soft-archive for owner-confirmed junk tenants. Rows stay in the database."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

logger = logging.getLogger(__name__)

KEEP_TENANTS = frozenset({"linas", "platform", "testuser", "apple-account", "chance-app", "linsss"})
_MEMORY: dict[str, str] = {}
_READY = False


def reset_archive_for_tests() -> None:
    global _READY
    _MEMORY.clear()
    _READY = False


def _ensure(session: Any) -> None:
    global _READY
    if _READY:
        return
    session.execute(
        text(
            """
            CREATE TABLE IF NOT EXISTS owner_portal_tenant_visibility (
                tenant_id TEXT PRIMARY KEY,
                hidden INTEGER NOT NULL,
                updated_at TEXT NOT NULL DEFAULT ''
            )
            """
        )
    )
    session.execute(
        text("ALTER TABLE owner_portal_tenant_visibility ADD COLUMN IF NOT EXISTS archived INTEGER NOT NULL DEFAULT 0")
    )
    session.execute(
        text("ALTER TABLE owner_portal_tenant_visibility ADD COLUMN IF NOT EXISTS email TEXT NOT NULL DEFAULT ''")
    )
    _READY = True


def archive_tenants(rows: list[dict[str, Any]]) -> list[str]:
    """Mark tenants archived. Protected and KEEP tenants are never written."""
    archived: list[str] = []
    now = datetime.now(UTC).isoformat()
    for row in rows:
        tenant_id = str(row.get("tenant_id") or "").strip().lower()
        if not tenant_id or tenant_id in KEEP_TENANTS:
            continue
        email = str(row.get("email") or "").strip().lower()
        _MEMORY[tenant_id] = email
        archived.append(tenant_id)
        try:
            from db.session import whatsapp_session

            with whatsapp_session(require=False) as session:
                if session is None:
                    continue
                _ensure(session)
                session.execute(
                    text(
                        """
                        INSERT INTO owner_portal_tenant_visibility
                            (tenant_id, hidden, updated_at, archived, email)
                        VALUES (:id, 1, :updated, 1, :email)
                        ON CONFLICT (tenant_id) DO UPDATE
                        SET hidden = 1, archived = 1, email = excluded.email, updated_at = excluded.updated_at
                        """
                    ),
                    {"id": tenant_id, "updated": now, "email": email},
                )
                session.commit()
        except Exception:
            logger.warning("archive row kept for this process only tenant=%s", tenant_id)
    return archived


def archived_tenant_ids() -> set[str]:
    found = {tenant_id for tenant_id in _MEMORY if tenant_id not in KEEP_TENANTS}
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=False) as session:
            if session is None:
                return found
            _ensure(session)
            rows = session.execute(
                text("SELECT tenant_id FROM owner_portal_tenant_visibility WHERE archived = 1")
            ).all()
    except Exception:
        return found
    for row in rows:
        tenant_id = str(row[0] or "").strip().lower()
        if tenant_id and tenant_id not in KEEP_TENANTS:
            found.add(tenant_id)
    return found


def archived_emails() -> set[str]:
    found = {email for email in _MEMORY.values() if email}
    try:
        from db.session import whatsapp_session

        with whatsapp_session(require=False) as session:
            if session is None:
                return found
            _ensure(session)
            rows = session.execute(
                text("SELECT email FROM owner_portal_tenant_visibility WHERE archived = 1 AND email <> ''")
            ).all()
    except Exception:
        return found
    found.update(str(row[0] or "").strip().lower() for row in rows if str(row[0] or "").strip())
    return found


def reuse_blocked(*, tenant_id: str, email: str = "") -> bool:
    tenant = (tenant_id or "").strip().lower()
    if tenant in KEEP_TENANTS:
        return False
    if tenant and tenant in archived_tenant_ids():
        return True
    mail = (email or "").strip().lower()
    return bool(mail and mail in archived_emails())
