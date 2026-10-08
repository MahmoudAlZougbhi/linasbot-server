"""Shared owner-chat rows so both production nodes see the same conversation."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text


def load_conversation(*, tenant_id: str, user_id: str, conversation_id: str) -> tuple[str, dict[str, Any] | None]:
    """Return (ok|missing|deleted|unavailable, payload). Postgres is authoritative when available."""
    rows = _select(
        """
        SELECT payload, deleted FROM owner_copilot_conversations
        WHERE id = :id AND tenant_id = :tenant AND user_id = :user
        """,
        {"id": conversation_id, "tenant": tenant_id, "user": user_id},
    )
    if rows is None:
        return "unavailable", None
    if not rows:
        return "missing", None
    if int(rows[0][1] or 0):
        return "deleted", None
    try:
        payload = json.loads(rows[0][0] or "{}")
    except json.JSONDecodeError:
        return "missing", None
    return ("ok", payload) if isinstance(payload, dict) else ("missing", None)


def list_conversations(*, tenant_id: str, user_id: str) -> tuple[str, list[dict[str, Any]]]:
    rows = _select(
        """
        SELECT payload FROM owner_copilot_conversations
        WHERE tenant_id = :tenant AND user_id = :user AND deleted = 0
        ORDER BY updated_at DESC
        """,
        {"tenant": tenant_id, "user": user_id},
    )
    if rows is None:
        return "unavailable", []
    items: list[dict[str, Any]] = []
    for row in rows:
        try:
            payload = json.loads(row[0] or "{}")
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            items.append(payload)
    return "ok", items


def save_conversation(payload: dict[str, Any]) -> None:
    from db.session import whatsapp_session

    body = json.dumps(payload, default=str)
    try:
        with whatsapp_session(require=False) as session:
            if session is None:
                return
            session.execute(
                text(
                    """
                    INSERT INTO owner_copilot_conversations
                      (id, tenant_id, user_id, title, created_at, updated_at, archived, deleted, payload)
                    VALUES
                      (:id, :tenant, :user, :title, :created, :updated, :archived, :deleted, :payload)
                    ON CONFLICT (id) DO UPDATE SET
                      title = excluded.title,
                      updated_at = excluded.updated_at,
                      archived = excluded.archived,
                      deleted = excluded.deleted,
                      payload = excluded.payload
                    """
                ),
                {
                    "id": payload["id"],
                    "tenant": payload["tenant_id"],
                    "user": payload["user_id"],
                    "title": payload.get("title") or "",
                    "created": float(payload.get("created_at") or 0),
                    "updated": float(payload.get("updated_at") or 0),
                    "archived": 1 if payload.get("archived") else 0,
                    "deleted": 1 if payload.get("deleted") else 0,
                    "payload": body,
                },
            )
    except Exception:
        return


def _select(sql: str, params: dict[str, Any]) -> list[Any] | None:
    from db.session import whatsapp_session

    try:
        with whatsapp_session(require=False) as session:
            if session is None:
                return None
            return list(session.execute(text(sql), params).all())
    except Exception:
        return None
