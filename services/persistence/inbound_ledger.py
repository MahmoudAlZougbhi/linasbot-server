"""Postgres inbound-event ledger. Replaces the Firestore inbound_events collection."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from db.session import whatsapp_session
from services.persistence.schema import ensure_schema

_ACTIVE = ("accepted", "queued", "processing", "failed")


def put_record(record: dict[str, Any]) -> dict[str, Any]:
    event_id = str(record.get("event_id") or "").strip()
    if not event_id:
        raise ValueError("event_id is required")
    tenant_id = str(record.get("tenant_id") or "").strip().lower()
    state = str(record.get("state") or "accepted")
    updated = float(record.get("updated_at") or 0)
    payload = json.dumps(record, default=str)
    with whatsapp_session(require=True) as session:
        ensure_schema(session)
        session.execute(
            text(
                """
                INSERT INTO linas_inbound_events (event_id, tenant_id, state, record_json, updated_at)
                VALUES (:event_id, :tenant_id, :state, :record_json, :updated_at)
                ON CONFLICT (event_id) DO UPDATE SET
                    tenant_id = excluded.tenant_id,
                    state = excluded.state,
                    record_json = excluded.record_json,
                    updated_at = excluded.updated_at
                """
            ),
            {
                "event_id": event_id,
                "tenant_id": tenant_id,
                "state": state,
                "record_json": payload,
                "updated_at": updated,
            },
        )
    return record


def get_record(event_id: str) -> dict[str, Any] | None:
    with whatsapp_session(require=True) as session:
        ensure_schema(session)
        row = session.execute(
            text("SELECT record_json FROM linas_inbound_events WHERE event_id = :event_id"),
            {"event_id": event_id},
        ).first()
    if row is None:
        return None
    parsed = json.loads(row[0])
    return parsed if isinstance(parsed, dict) else None


def list_active(*, limit: int = 32) -> list[dict[str, Any]]:
    names = []
    params: dict[str, Any] = {"limit": max(1, min(int(limit), 200))}
    for index, state in enumerate(_ACTIVE):
        key = f"state_{index}"
        names.append(f":{key}")
        params[key] = state
    with whatsapp_session(require=True) as session:
        ensure_schema(session)
        rows = session.execute(
            text(
                f"""
                SELECT record_json FROM linas_inbound_events
                WHERE state IN ({", ".join(names)})
                ORDER BY updated_at ASC
                LIMIT :limit
                """
            ),
            params,
        ).all()
    out: list[dict[str, Any]] = []
    for row in rows:
        parsed = json.loads(row[0])
        if isinstance(parsed, dict):
            out.append(parsed)
    return out
