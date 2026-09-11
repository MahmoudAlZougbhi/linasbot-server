"""Optional Postgres session for message ledger / daily edits / expenses.

Memory remains the unit-test store. Postgres is used only when billing PG is
configured and the 20260910_msg_billing tables exist. Missing tables are not
pretended to be durable success.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from sqlalchemy import text

_TABLES = (
    "customer_ai_message_lots",
    "customer_ai_message_reservations",
    "customer_ai_daily_edits",
    "customer_ai_daily_edit_policies",
    "customer_ai_expense_events",
)


class MessageStoreUnavailable(RuntimeError):
    code = "MESSAGE_STORE_UNAVAILABLE"


def memory_forced() -> bool:
    return (os.getenv("LINAS_MESSAGE_STORE") or "").strip().lower() in {"memory", "file"}


def store_backend() -> str:
    if memory_forced() or not postgres_requested():
        return "memory"
    with optional_message_session() as session:
        if session is not None:
            return "postgres"
    return "memory_fallback"


def postgres_requested() -> bool:
    if memory_forced():
        return False
    try:
        from services.billing_backend import billing_uses_postgres

        return billing_uses_postgres()
    except Exception:
        return False


def tables_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        dialect = bind.dialect.name
        for table in _TABLES:
            if dialect == "sqlite":
                row = session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                    {"n": table},
                ).fetchone()
            else:
                row = session.execute(
                    text("SELECT to_regclass(:n)"),
                    {"n": table},
                ).fetchone()
            if row is None or row[0] is None:
                return False
        return True
    except Exception:
        return False


@contextmanager
def optional_message_session(*, require: bool = False) -> Iterator[Any | None]:
    if memory_forced() or not postgres_requested():
        if require:
            raise MessageStoreUnavailable("message store requires postgres")
        yield None
        return
    try:
        from services.billing_backend import BillingBackendError, require_billing_pg_session

        with require_billing_pg_session() as session:
            if not tables_ready(session):
                if require:
                    raise MessageStoreUnavailable("message billing tables are not applied")
                yield None
                return
            yield session
    except BillingBackendError as exc:
        if require:
            raise MessageStoreUnavailable(str(exc)) from exc
        yield None
