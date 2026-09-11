"""Optional SQL persistence for processing attempt and concurrency budgets."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import text

JOB_STALE_SECONDS = 3600


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        names = ("customer_ai_processing_attempts", "customer_ai_processing_jobs")
        if bind.dialect.name == "sqlite":
            for name in names:
                row = session.execute(
                    text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
                    {"n": name},
                ).first()
                if not (row and row[0]):
                    return False
            return True
        for name in names:
            row = session.execute(text("SELECT to_regclass(:n)"), {"n": name}).first()
            if not (row and row[0]):
                return False
        return True
    except Exception:
        return False


def pg_reset(session: Any) -> None:
    session.execute(text("DELETE FROM customer_ai_processing_jobs"))
    session.execute(text("DELETE FROM customer_ai_processing_attempts"))


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _cutoff() -> str:
    return (datetime.now(UTC) - timedelta(seconds=JOB_STALE_SECONDS)).isoformat()


def pg_consume_attempt(session: Any, *, tenant_id: str, day_id: str, limit: int) -> int | None:
    session.execute(
        text(
            "INSERT INTO customer_ai_processing_attempts (tenant_id, day_id, used, updated_at) "
            "VALUES (:tid, :day, 1, :ts) "
            "ON CONFLICT (tenant_id, day_id) DO UPDATE SET used = customer_ai_processing_attempts.used + 1, "
            "updated_at=:ts"
        ),
        {"tid": tenant_id, "day": day_id, "ts": _now()},
    )
    used = int(
        session.execute(
            text("SELECT used FROM customer_ai_processing_attempts WHERE tenant_id = :tid AND day_id = :day"),
            {"tid": tenant_id, "day": day_id},
        ).scalar_one()
    )
    if used > limit:
        session.execute(
            text(
                "UPDATE customer_ai_processing_attempts SET used = used - 1, updated_at=:ts "
                "WHERE tenant_id = :tid AND day_id = :day AND used > 0"
            ),
            {"tid": tenant_id, "day": day_id, "ts": _now()},
        )
        return None
    return used


def pg_attempt_used(session: Any, *, tenant_id: str = "", day_id: str) -> int:
    if tenant_id:
        row = session.execute(
            text("SELECT used FROM customer_ai_processing_attempts WHERE tenant_id = :tid AND day_id = :day"),
            {"tid": tenant_id, "day": day_id},
        ).first()
        return int(row[0] or 0) if row else 0
    value = session.execute(
        text("SELECT COALESCE(SUM(used), 0) FROM customer_ai_processing_attempts WHERE day_id = :day"),
        {"day": day_id},
    ).scalar_one()
    return int(value or 0)


def pg_begin_job(session: Any, *, tenant_id: str, limit: int) -> str | None:
    job_id = uuid4().hex
    session.execute(
        text(
            "INSERT INTO customer_ai_processing_jobs (job_id, tenant_id, created_at) "
            "VALUES (:jid, :tid, :ts)"
        ),
        {"jid": job_id, "tid": tenant_id, "ts": _now()},
    )
    current = pg_job_count(session, tenant_id=tenant_id)
    if current > limit:
        session.execute(text("DELETE FROM customer_ai_processing_jobs WHERE job_id = :jid"), {"jid": job_id})
        return None
    return job_id


def pg_end_job(session: Any, job_id: str) -> None:
    session.execute(text("DELETE FROM customer_ai_processing_jobs WHERE job_id = :jid"), {"jid": job_id})


def pg_end_latest_job(session: Any, tenant_id: str) -> None:
    row = session.execute(
        text(
            "SELECT job_id FROM customer_ai_processing_jobs WHERE tenant_id = :tid "
            "ORDER BY created_at DESC, job_id DESC LIMIT 1"
        ),
        {"tid": tenant_id},
    ).first()
    if row and row[0]:
        pg_end_job(session, str(row[0]))


def pg_job_count(session: Any, *, tenant_id: str = "") -> int:
    sql = "SELECT COUNT(*) FROM customer_ai_processing_jobs WHERE created_at > :cutoff"
    params: dict[str, Any] = {"cutoff": _cutoff()}
    if tenant_id:
        sql += " AND tenant_id = :tid"
        params["tid"] = tenant_id
    return int(session.execute(text(sql), params).scalar_one() or 0)


def pg_tenant_ids(session: Any) -> list[str]:
    rows = session.execute(
        text(
            "SELECT tenant_id FROM customer_ai_processing_attempts "
            "UNION SELECT tenant_id FROM customer_ai_processing_jobs"
        )
    ).all()
    return sorted({str(row[0]) for row in rows if row and row[0]})


def pg_tenants_with_jobs(session: Any) -> int:
    return int(
        session.execute(
            text(
                "SELECT COUNT(DISTINCT tenant_id) FROM customer_ai_processing_jobs "
                "WHERE created_at > :cutoff"
            ),
            {"cutoff": _cutoff()},
        ).scalar_one()
        or 0
    )
