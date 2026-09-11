"""Durable daily-edit limits. Memory remains the test store."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

PLATFORM_TENANT = "__platform__"


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_daily_edit_policies'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_daily_edit_policies')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def pg_load_limits(session: Any) -> tuple[int | None, dict[str, int]]:
    rows = session.execute(
        text("SELECT tenant_id, limit_value FROM customer_ai_daily_edit_policies")
    ).mappings().all()
    baseline = None
    overrides: dict[str, int] = {}
    for row in rows:
        tid = str(row["tenant_id"] or "")
        value = int(row["limit_value"])
        if tid == PLATFORM_TENANT:
            baseline = value
        else:
            overrides[tid] = value
    return baseline, overrides


def pg_upsert_limit(session: Any, *, tenant_id: str, limit_value: int, source: str) -> None:
    session.execute(
        text(
            "INSERT INTO customer_ai_daily_edit_policies (tenant_id, limit_value, source) "
            "VALUES (:tid, :limit, :source) "
            "ON CONFLICT (tenant_id) DO UPDATE SET limit_value = :limit, source = :source, "
            "updated_at = CURRENT_TIMESTAMP"
        ),
        {"tid": tenant_id, "limit": limit_value, "source": source},
    )


def pg_delete_limit(session: Any, tenant_id: str) -> None:
    session.execute(
        text("DELETE FROM customer_ai_daily_edit_policies WHERE tenant_id = :tid"),
        {"tid": tenant_id},
    )
