"""Delete expired rows. Callers pass the cutoff; nothing here runs on a timer by itself."""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.engine import Engine

REALTIME_TTL_SECONDS = 24 * 60 * 60
TRACE_TTL_SECONDS = 30 * 24 * 60 * 60
INBOUND_PAYLOAD_TTL_SECONDS = 30 * 24 * 60 * 60
INBOUND_ID_TTL_SECONDS = 90 * 24 * 60 * 60
DLQ_TTL_SECONDS = 30 * 24 * 60 * 60


def _delete_before(engine: Engine, table: str, column: str, cutoff: float) -> int:
    with engine.begin() as conn:
        result = conn.execute(
            text(f"DELETE FROM {table} WHERE {column} < :cutoff"),
            {"cutoff": cutoff},
        )
    return int(result.rowcount or 0)


def purge_realtime_events(engine: Engine, *, now: float) -> int:
    return _delete_before(engine, "realtime_events", "created_at", now - REALTIME_TTL_SECONDS)


def purge_dead_letters(engine: Engine, *, now: float) -> int:
    return _delete_before(engine, "platform_job_dlq", "created_at", now - DLQ_TTL_SECONDS)


def purge_inbound_payloads(engine: Engine, *, now: float) -> int:
    """Keep the idempotency key. Drop the payload body after 30 days."""
    cutoff = now - INBOUND_PAYLOAD_TTL_SECONDS
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                UPDATE inbound_events
                SET payload = '{}', status = 'expired'
                WHERE created_at < :cutoff AND status != 'expired'
                """
            ),
            {"cutoff": cutoff},
        )
    return int(result.rowcount or 0)
