"""Optional SQL persistence for the platform-admin message catalog draft."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

ROW_ID = "current"


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_catalog_admin'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_catalog_admin')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def pg_reset(session: Any) -> None:
    session.execute(text("DELETE FROM customer_ai_catalog_admin"))


def _decode_dict(raw: Any) -> dict[str, Any]:
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = {}
    return dict(value) if isinstance(value, dict) else {}


def _decode_list(raw: Any) -> list[dict[str, Any]]:
    value = raw
    if isinstance(value, str):
        try:
            value = json.loads(value)
        except Exception:
            value = []
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict)]


def pg_upsert(
    session: Any,
    *,
    draft: dict[str, Any],
    revision: int,
    published: bool,
    audit: list[dict[str, Any]],
) -> None:
    session.execute(
        text(
            "INSERT INTO customer_ai_catalog_admin ("
            "row_id, draft, revision, published, audit, updated_at"
            ") VALUES ("
            ":row_id, :draft, :revision, :published, :audit, :updated_at"
            ") ON CONFLICT (row_id) DO UPDATE SET "
            "draft=:draft, revision=:revision, published=:published, audit=:audit, updated_at=:updated_at"
        ),
        {
            "row_id": ROW_ID,
            "draft": json.dumps(draft or {}, ensure_ascii=False),
            "revision": int(revision or 1),
            "published": bool(published),
            "audit": json.dumps(audit[-50:], ensure_ascii=False),
            "updated_at": datetime.now(UTC).isoformat(),
        },
    )


def pg_load(session: Any) -> dict[str, Any] | None:
    row = session.execute(
        text("SELECT draft, revision, published, audit FROM customer_ai_catalog_admin WHERE row_id = :rid"),
        {"rid": ROW_ID},
    ).mappings().first()
    if row is None:
        return None
    return {
        "draft": _decode_dict(row.get("draft")),
        "revision": int(row.get("revision") or 1),
        "published": bool(row.get("published")),
        "audit": _decode_list(row.get("audit")),
    }
