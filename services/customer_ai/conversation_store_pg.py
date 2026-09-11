"""Optional SQL persistence for Brain conversation state. Not a customer wallet."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_conversations'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_conversations')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def pg_reset(session: Any) -> None:
    session.execute(text("DELETE FROM customer_ai_conversations"))


def _dump(value: Any) -> str:
    return json.dumps(value if value is not None else [], ensure_ascii=False)


def _load_list(raw: Any) -> list[Any]:
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = []
    return list(value) if isinstance(value, list) else []


def _load_dict(raw: Any) -> dict[str, Any]:
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {}
    return dict(value) if isinstance(value, dict) else {}


def pg_upsert(
    session: Any,
    *,
    store_key: str,
    tenant_id: str,
    conversation_id: str,
    payload: dict[str, Any],
) -> None:
    session.execute(
        text(
            "INSERT INTO customer_ai_conversations ("
            "store_key, tenant_id, conversation_id, state, pending, history, updated_at"
            ") VALUES ("
            ":store_key, :tenant_id, :conversation_id, :state, :pending, :history, :updated_at"
            ") ON CONFLICT (store_key) DO UPDATE SET "
            "state=:state, pending=:pending, history=:history, updated_at=:updated_at"
        ),
        {
            "store_key": store_key,
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "state": _dump(payload.get("state") or {}),
            "pending": _dump(payload.get("pending") or []),
            "history": _dump(payload.get("history") or []),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )


def pg_tenant_ids(session: Any) -> list[str]:
    rows = session.execute(text("SELECT DISTINCT tenant_id FROM customer_ai_conversations")).all()
    return sorted({str(row[0]) for row in rows if row and row[0]})


def pg_get(session: Any, store_key: str) -> dict[str, Any] | None:
    row = session.execute(
        text(
            "SELECT state, pending, history FROM customer_ai_conversations WHERE store_key = :key"
        ),
        {"key": store_key},
    ).mappings().first()
    if row is None:
        return None
    return {
        "state": _load_dict(row.get("state")),
        "pending": _load_list(row.get("pending")),
        "history": _load_list(row.get("history")),
    }
