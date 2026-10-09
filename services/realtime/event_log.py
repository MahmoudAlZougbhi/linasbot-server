"""Persist realtime events, then fan them out. Resume reads Postgres."""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from services.platform.feature_flags import flag_value


def realtime_mode() -> str:
    mode = flag_value("realtime_backend")
    return mode if mode in {"local", "valkey"} else "local"


def ensure_schema(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS realtime_events (
                    id INTEGER PRIMARY KEY,
                    tenant_id TEXT NOT NULL,
                    channel TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at DOUBLE PRECISION NOT NULL
                )
                """
            )
        )


def append_event(engine: Engine, *, tenant_id: str, channel: str, payload: dict[str, Any]) -> int:
    ensure_schema(engine)
    now = time.time()
    body = json.dumps(payload, separators=(",", ":"), default=str)
    with engine.begin() as conn:
        row = conn.execute(text("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM realtime_events")).one()
        event_id = int(row.next_id)
        conn.execute(
            text(
                """
                INSERT INTO realtime_events (id, tenant_id, channel, payload, created_at)
                VALUES (:id, :tenant, :channel, :payload, :now)
                """
            ),
            {"id": event_id, "tenant": tenant_id, "channel": channel, "payload": body, "now": now},
        )
    return event_id


def replay_after(engine: Engine, *, tenant_id: str, last_event_id: int) -> list[dict[str, Any]]:
    ensure_schema(engine)
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id, channel, payload FROM realtime_events
                WHERE tenant_id = :tenant AND id > :last_id
                ORDER BY id
                """
            ),
            {"tenant": tenant_id, "last_id": last_event_id},
        ).fetchall()
    return [{"id": int(row.id), "channel": row.channel, "payload": json.loads(row.payload)} for row in rows]
