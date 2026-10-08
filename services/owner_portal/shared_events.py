"""Shared Postgres rows for owner audit and activity flow."""

from __future__ import annotations

import json
import uuid
from contextlib import AbstractContextManager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

AUDIT_SQL = """
CREATE TABLE IF NOT EXISTS owner_portal_audit_events (
    id TEXT PRIMARY KEY,
    actor_user_id TEXT NOT NULL DEFAULT '',
    action TEXT NOT NULL DEFAULT '',
    tenant_id TEXT NOT NULL DEFAULT '',
    details TEXT NOT NULL DEFAULT '{}',
    created_at DOUBLE PRECISION NOT NULL DEFAULT 0
)
"""
FLOW_SQL = """
CREATE TABLE IF NOT EXISTS owner_portal_flow_events (
    id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT '',
    channel TEXT NOT NULL DEFAULT '',
    message_type TEXT NOT NULL DEFAULT 'text',
    created_at TEXT NOT NULL DEFAULT '',
    payload TEXT NOT NULL DEFAULT '{}'
)
"""


def ensure_tables(session: Any) -> None:
    session.execute(text(AUDIT_SQL))
    session.execute(text(FLOW_SQL))
    session.execute(
        text("CREATE INDEX IF NOT EXISTS ix_owner_portal_audit_created ON owner_portal_audit_events (created_at)")
    )
    session.execute(
        text(
            "CREATE INDEX IF NOT EXISTS ix_owner_portal_flow_tenant_created "
            "ON owner_portal_flow_events (tenant_id, created_at)"
        )
    )


def _session() -> AbstractContextManager[Any]:
    from db.session import whatsapp_session

    return whatsapp_session(require=False)


def insert_audit_event(row: dict[str, Any]) -> bool:
    try:
        with _session() as session:
            if session is None:
                return False
            ensure_tables(session)
            session.execute(
                text(
                    """
                    INSERT INTO owner_portal_audit_events
                      (id, actor_user_id, action, tenant_id, details, created_at)
                    VALUES (:id, :actor, :action, :tenant, :details, :created)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": str(row.get("id") or uuid.uuid4().hex),
                    "actor": str(row.get("actor_user_id") or ""),
                    "action": str(row.get("action") or ""),
                    "tenant": str(row.get("tenant_id") or ""),
                    "details": json.dumps(row.get("details") or {}, default=str),
                    "created": float(row.get("created_at") or 0),
                },
            )
        return True
    except Exception:
        return False


def list_audit_events(*, limit: int = 50) -> list[dict[str, Any]] | None:
    try:
        with _session() as session:
            if session is None:
                return None
            ensure_tables(session)
            rows = session.execute(
                text(
                    """
                    SELECT id, actor_user_id, action, tenant_id, details, created_at
                    FROM owner_portal_audit_events
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": max(1, min(limit, 200))},
            ).all()
    except Exception:
        return None
    out = []
    for row in rows:
        try:
            details = json.loads(row[4] or "{}")
        except json.JSONDecodeError:
            details = {}
        out.append(
            {
                "id": row[0],
                "actor_user_id": row[1],
                "action": row[2],
                "tenant_id": row[3],
                "details": details,
                "created_at": row[5],
            }
        )
    return out


def insert_flow_event(entry: dict[str, Any]) -> bool:
    try:
        with _session() as session:
            if session is None:
                return False
            ensure_tables(session)
            created = str(entry.get("timestamp") or datetime.now(UTC).isoformat())
            session.execute(
                text(
                    """
                    INSERT INTO owner_portal_flow_events
                      (id, tenant_id, channel, message_type, created_at, payload)
                    VALUES (:id, :tenant, :channel, :message_type, :created, :payload)
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "id": str(entry.get("message_id") or entry.get("id") or uuid.uuid4().hex),
                    "tenant": str(entry.get("tenant_id") or ""),
                    "channel": str(entry.get("channel") or ""),
                    "message_type": str(entry.get("message_type") or "text"),
                    "created": created,
                    "payload": json.dumps(entry, default=str),
                },
            )
        return True
    except Exception:
        return False


def list_flow_events(*, tenant_id: str | None = None, limit: int = 50) -> list[dict[str, Any]] | None:
    try:
        with _session() as session:
            if session is None:
                return None
            ensure_tables(session)
            params: dict[str, Any] = {"limit": max(1, min(limit, 200))}
            where = ""
            if tenant_id:
                where = "WHERE tenant_id = :tenant"
                params["tenant"] = tenant_id
            rows = session.execute(
                text(
                    f"""
                    SELECT payload FROM owner_portal_flow_events
                    {where}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).all()
    except Exception:
        return None
    out = []
    for row in rows:
        try:
            item = json.loads(row[0] or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            out.append(item)
    return out
