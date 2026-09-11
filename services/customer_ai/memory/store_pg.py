"""Durable Postgres-backed Customer Brain memory + rolling summaries."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_memory_facts'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_memory_facts')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def summary_table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_memory_summaries'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_memory_summaries')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def upsert_fact(
    session: Any,
    *,
    tenant_id: str,
    customer_id: str,
    key: str,
    value: str,
    source_message_ids: list[str] | None = None,
    confidence: float = 0.7,
    fact_type: str = "preference",
    expires_at: str = "",
) -> None:
    now = datetime.now(UTC).isoformat()
    fact_id = f"{tenant_id}:{customer_id}:{key}"[:128]
    session.execute(
        text(
            """
            INSERT INTO customer_ai_memory_facts (
                id, tenant_id, customer_id, fact_type, fact_key, fact_value,
                source_message_ids, confidence, status, expires_at, created_at, updated_at
            ) VALUES (
                :id, :tenant_id, :customer_id, :fact_type, :fact_key, :fact_value,
                :source_message_ids, :confidence, 'active', :expires_at, :created_at, :updated_at
            )
            ON CONFLICT (tenant_id, customer_id, fact_key) DO UPDATE SET
                fact_value = EXCLUDED.fact_value,
                source_message_ids = EXCLUDED.source_message_ids,
                confidence = EXCLUDED.confidence,
                fact_type = EXCLUDED.fact_type,
                status = 'active',
                expires_at = EXCLUDED.expires_at,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": fact_id,
            "tenant_id": tenant_id,
            "customer_id": customer_id,
            "fact_type": fact_type[:64],
            "fact_key": key[:80],
            "fact_value": value[:500],
            "source_message_ids": json.dumps(list(source_message_ids or [])[:8], ensure_ascii=False),
            "confidence": float(confidence),
            "expires_at": expires_at or None,
            "created_at": now,
            "updated_at": now,
        },
    )


def list_facts(session: Any, *, tenant_id: str, customer_id: str, limit: int = 12) -> list[dict[str, Any]]:
    rows = session.execute(
        text(
            """
            SELECT fact_key, fact_value, source_message_ids, confidence, fact_type, updated_at, expires_at
            FROM customer_ai_memory_facts
            WHERE tenant_id = :tenant_id AND customer_id = :customer_id AND status = 'active'
            ORDER BY updated_at DESC
            LIMIT :limit
            """
        ),
        {"tenant_id": tenant_id, "customer_id": customer_id, "limit": max(1, limit)},
    ).mappings()
    out: list[dict[str, Any]] = []
    for row in rows:
        refs = row.get("source_message_ids")
        if isinstance(refs, str):
            try:
                refs = json.loads(refs)
            except Exception:
                refs = []
        out.append(
            {
                "key": str(row.get("fact_key") or ""),
                "value": str(row.get("fact_value") or ""),
                "source_message_ids": list(refs or []),
                "confidence": float(row.get("confidence") or 0.0),
                "type": str(row.get("fact_type") or ""),
                "updated_at": str(row.get("updated_at") or ""),
            }
        )
    return out


def upsert_summary(
    session: Any,
    *,
    tenant_id: str,
    conversation_id: str,
    summary: str,
    source_message_ids: list[str] | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    sid = f"{tenant_id}:{conversation_id}"[:128]
    session.execute(
        text(
            """
            INSERT INTO customer_ai_memory_summaries (
                id, tenant_id, conversation_id, summary_text, source_message_ids, updated_at
            ) VALUES (
                :id, :tenant_id, :conversation_id, :summary_text, :source_message_ids, :updated_at
            )
            ON CONFLICT (tenant_id, conversation_id) DO UPDATE SET
                summary_text = EXCLUDED.summary_text,
                source_message_ids = EXCLUDED.source_message_ids,
                updated_at = EXCLUDED.updated_at
            """
        ),
        {
            "id": sid,
            "tenant_id": tenant_id,
            "conversation_id": conversation_id,
            "summary_text": (summary or "")[:4000],
            "source_message_ids": json.dumps(list(source_message_ids or [])[:50], ensure_ascii=False),
            "updated_at": now,
        },
    )


def get_summary(session: Any, *, tenant_id: str, conversation_id: str) -> dict[str, Any] | None:
    row = session.execute(
        text(
            """
            SELECT summary_text, source_message_ids, updated_at
            FROM customer_ai_memory_summaries
            WHERE tenant_id = :tenant_id AND conversation_id = :conversation_id
            """
        ),
        {"tenant_id": tenant_id, "conversation_id": conversation_id},
    ).mappings().first()
    if row is None:
        return None
    refs = row.get("source_message_ids")
    if isinstance(refs, str):
        try:
            refs = json.loads(refs)
        except Exception:
            refs = []
    return {
        "summary": str(row.get("summary_text") or ""),
        "source_message_ids": list(refs or []),
        "updated_at": str(row.get("updated_at") or ""),
    }
