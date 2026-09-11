"""Optional durable tables that must exist before activation can be honest.

Core message-store tables stay in ``pg_store._TABLES``. Missing optional
tables must not disable the whole store, but they do block verified
activation. This report never flips flags.
"""

from __future__ import annotations

from sqlalchemy import text

from services.membership.pg_store import optional_message_session, store_backend

DURABLE_TABLES = (
    "customer_ai_message_lots",
    "customer_ai_message_reservations",
    "customer_ai_daily_edits",
    "customer_ai_daily_edit_policies",
    "customer_ai_expense_events",
    "customer_ai_pending_settlements",
    "customer_ai_outbox",
    "customer_ai_conversations",
    "customer_ai_catalog_admin",
    "customer_ai_credit_reservation_index",
    "customer_ai_processing_attempts",
    "customer_ai_processing_jobs",
)


def _table_exists(session, name: str) -> bool:
    try:
        bind = session.get_bind()
        dialect = getattr(bind.dialect, "name", "") if bind is not None else ""
        if dialect == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                {"n": name},
            ).fetchone()
        else:
            row = session.execute(text("SELECT to_regclass(:n)"), {"n": name}).fetchone()
        return bool(row and row[0])
    except Exception:
        return False


def durable_table_report() -> dict:
    present = {name: False for name in DURABLE_TABLES}
    with optional_message_session() as session:
        if session is None:
            return {
                "ready": False,
                "store": store_backend(),
                "tables": present,
            }
        for name in DURABLE_TABLES:
            present[name] = _table_exists(session, name)
    return {
        "ready": all(present.values()),
        "store": store_backend(),
        "tables": present,
    }
