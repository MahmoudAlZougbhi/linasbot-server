"""Postgres daily AI Setup edit counters."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services.membership.daily_edits import DailyEditDecision, DailyEditLimitError, effective_limit


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_daily_edits'")
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_daily_edits')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def pg_tenant_ids(session: Any, window_id: str = "") -> list[str]:
    sql = "SELECT DISTINCT tenant_id FROM customer_ai_daily_edits"
    params: dict[str, Any] = {}
    if window_id:
        sql += " WHERE window_id = :wid"
        params["wid"] = window_id
    rows = session.execute(text(sql), params).all()
    return [str(row[0]) for row in rows if row and row[0]]


def pg_operation_ids(session: Any, tenant_id: str, window_id: str) -> dict[str, str]:
    rows = session.execute(
        text("SELECT operation_id, status FROM customer_ai_daily_edits WHERE tenant_id = :tid AND window_id = :wid"),
        {"tid": tenant_id, "wid": window_id},
    ).all()
    return {str(row[0]): str(row[1]) for row in rows if row and row[0]}


def pg_counts(session: Any, tenant_id: str, window_id: str) -> tuple[int, int]:
    used = session.execute(
        text(
            "SELECT COUNT(*) FROM customer_ai_daily_edits "
            "WHERE tenant_id = :tid AND window_id = :wid AND status = 'committed'"
        ),
        {"tid": tenant_id, "wid": window_id},
    ).scalar()
    reserved = session.execute(
        text(
            "SELECT COUNT(*) FROM customer_ai_daily_edits "
            "WHERE tenant_id = :tid AND window_id = :wid AND status = 'reserved'"
        ),
        {"tid": tenant_id, "wid": window_id},
    ).scalar()
    return int(used or 0), int(reserved or 0)


def pg_reserve(session: Any, *, tenant_id: str, operation_id: str, window_id: str, reset_at: str) -> DailyEditDecision:
    limit, source = effective_limit(tenant_id)
    existing = session.execute(
        text(
            "SELECT status FROM customer_ai_daily_edits "
            "WHERE tenant_id = :tid AND window_id = :wid AND operation_id = :op"
        ),
        {"tid": tenant_id, "wid": window_id, "op": operation_id},
    ).first()
    used, reserved = pg_counts(session, tenant_id, window_id)
    if existing is not None:
        remaining = max(0, limit - used - reserved)
        return DailyEditDecision(True, used, reserved, remaining, limit, window_id, reset_at, source=source)
    if used + reserved >= limit:
        raise DailyEditLimitError(
            DailyEditDecision(
                False, used, reserved, 0, limit, window_id, reset_at, source=source, reason="AI_SETUP_DAILY_LIMIT"
            )
        )
    session.execute(
        text(
            "INSERT INTO customer_ai_daily_edits (tenant_id, window_id, operation_id, status) "
            "VALUES (:tid, :wid, :op, 'reserved')"
        ),
        {"tid": tenant_id, "wid": window_id, "op": operation_id},
    )
    used, reserved = pg_counts(session, tenant_id, window_id)
    remaining = max(0, limit - used - reserved)
    return DailyEditDecision(True, used, reserved, remaining, limit, window_id, reset_at, source=source)


def pg_commit(session: Any, *, tenant_id: str, operation_id: str, window_id: str, reset_at: str) -> DailyEditDecision:
    session.execute(
        text(
            "UPDATE customer_ai_daily_edits SET status = 'committed' "
            "WHERE tenant_id = :tid AND window_id = :wid AND operation_id = :op"
        ),
        {"tid": tenant_id, "wid": window_id, "op": operation_id},
    )
    if (
        session.execute(
            text(
                "SELECT 1 FROM customer_ai_daily_edits "
                "WHERE tenant_id = :tid AND window_id = :wid AND operation_id = :op"
            ),
            {"tid": tenant_id, "wid": window_id, "op": operation_id},
        ).first()
        is None
    ):
        session.execute(
            text(
                "INSERT INTO customer_ai_daily_edits (tenant_id, window_id, operation_id, status) "
                "VALUES (:tid, :wid, :op, 'committed')"
            ),
            {"tid": tenant_id, "wid": window_id, "op": operation_id},
        )
    limit, source = effective_limit(tenant_id)
    used, reserved = pg_counts(session, tenant_id, window_id)
    remaining = max(0, limit - used - reserved)
    return DailyEditDecision(True, used, reserved, remaining, limit, window_id, reset_at, source=source)


def pg_release(session: Any, *, tenant_id: str, operation_id: str, window_id: str, reset_at: str) -> DailyEditDecision:
    session.execute(
        text(
            "UPDATE customer_ai_daily_edits SET status = 'released' "
            "WHERE tenant_id = :tid AND window_id = :wid AND operation_id = :op AND status = 'reserved'"
        ),
        {"tid": tenant_id, "wid": window_id, "op": operation_id},
    )
    limit, source = effective_limit(tenant_id)
    used, reserved = pg_counts(session, tenant_id, window_id)
    remaining = max(0, limit - used - reserved)
    return DailyEditDecision(True, used, reserved, remaining, limit, window_id, reset_at, source=source)
