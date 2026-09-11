"""Operational processing budgets. Not a customer message debit."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

DEFAULT_CONCURRENT_JOBS = 2
DEFAULT_DAILY_PROVIDER_ATTEMPTS = 40
DEFAULT_IMPORT_ITEMS = 200

_LOCK = threading.Lock()
_CONCURRENT: dict[str, int] = {}
_ATTEMPTS: dict[str, dict[str, int]] = {}
_JOBS: dict[str, list[str]] = {}


@dataclass(frozen=True)
class BudgetDecision:
    allow: bool
    code: str = "ok"
    remaining: int = 0
    limit: int = 0


class ProcessingBudgetError(Exception):
    def __init__(self, decision: BudgetDecision) -> None:
        super().__init__(decision.code)
        self.decision = decision
        self.code = decision.code


def reset_processing_budgets_for_tests() -> None:
    with _LOCK:
        _CONCURRENT.clear()
        _ATTEMPTS.clear()
        _JOBS.clear()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.processing_budgets_pg import pg_reset, table_ready

        if table_ready(session):
            pg_reset(session)


def _day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@contextmanager
def _session() -> Iterator[Any | None]:
    from services.membership.pg_store import memory_forced, optional_message_session

    if memory_forced():
        yield None
        return
    with optional_message_session() as session:
        yield session


def begin_job(tenant_id: str, *, limit: int = DEFAULT_CONCURRENT_JOBS) -> BudgetDecision:
    tid = tenant_id.strip()
    with _LOCK:
        mem_jobs = _CONCURRENT.get(tid, 0)
    with _session() as session:
        if session is not None:
            from services.membership.processing_budgets_pg import pg_begin_job, pg_job_count, table_ready

            if table_ready(session):
                sql_jobs = pg_job_count(session, tenant_id=tid)
                if sql_jobs + mem_jobs >= limit:
                    raise ProcessingBudgetError(BudgetDecision(False, "PROCESSING_CONCURRENCY", 0, limit))
                job_id = pg_begin_job(session, tenant_id=tid, limit=limit)
                if job_id is None:
                    raise ProcessingBudgetError(BudgetDecision(False, "PROCESSING_CONCURRENCY", 0, limit))
                with _LOCK:
                    _JOBS.setdefault(tid, []).append(job_id)
                return BudgetDecision(
                    True,
                    remaining=max(0, limit - pg_job_count(session, tenant_id=tid) - mem_jobs),
                    limit=limit,
                )
    with _LOCK:
        current = _CONCURRENT.get(tid, 0)
        if current >= limit:
            raise ProcessingBudgetError(BudgetDecision(False, "PROCESSING_CONCURRENCY", 0, limit))
        _CONCURRENT[tid] = current + 1
        return BudgetDecision(True, remaining=limit - current - 1, limit=limit)


def end_job(tenant_id: str) -> None:
    tid = tenant_id.strip()
    job_id = ""
    with _LOCK:
        jobs = _JOBS.get(tid) or []
        if jobs:
            job_id = jobs.pop()
        else:
            _CONCURRENT[tid] = max(0, _CONCURRENT.get(tid, 0) - 1)
            return
    with _session() as session:
        if session is None:
            return
        from services.membership.processing_budgets_pg import pg_end_job, table_ready

        if table_ready(session):
            pg_end_job(session, job_id)


def consume_attempt(tenant_id: str, *, limit: int = DEFAULT_DAILY_PROVIDER_ATTEMPTS) -> BudgetDecision:
    tid = tenant_id.strip()
    day = _day()
    with _LOCK:
        mem_used = _ATTEMPTS.get(tid, {}).get(day, 0)
    with _session() as session:
        if session is not None:
            from services.membership.processing_budgets_pg import pg_attempt_used, pg_consume_attempt, table_ready

            if table_ready(session):
                if pg_attempt_used(session, tenant_id=tid, day_id=day) + mem_used >= limit:
                    raise ProcessingBudgetError(BudgetDecision(False, "PROCESSING_DAILY_ATTEMPTS", 0, limit))
                used = pg_consume_attempt(session, tenant_id=tid, day_id=day, limit=limit)
                if used is None:
                    raise ProcessingBudgetError(BudgetDecision(False, "PROCESSING_DAILY_ATTEMPTS", 0, limit))
                return BudgetDecision(True, remaining=max(0, limit - used - mem_used), limit=limit)
    with _LOCK:
        used = _ATTEMPTS.setdefault(tid, {}).get(day, 0)
        if used >= limit:
            raise ProcessingBudgetError(BudgetDecision(False, "PROCESSING_DAILY_ATTEMPTS", 0, limit))
        _ATTEMPTS[tid][day] = used + 1
        return BudgetDecision(True, remaining=limit - used - 1, limit=limit)


def known_processing_tenant_ids() -> list[str]:
    """Tenants already present on processing rows. Do not invent ids."""
    with _LOCK:
        ids = set(_ATTEMPTS) | set(_JOBS) | set(_CONCURRENT)
    with _session() as session:
        if session is not None:
            from services.membership.processing_budgets_pg import pg_tenant_ids, table_ready

            if table_ready(session):
                ids.update(pg_tenant_ids(session))
    return sorted(tid for tid in ids if tid)


def reject_oversized_import(item_count: int, *, limit: int = DEFAULT_IMPORT_ITEMS) -> None:
    if item_count > limit:
        raise ProcessingBudgetError(BudgetDecision(False, "PROCESSING_IMPORT_SIZE", 0, limit))


def _memory_status(tenant_id: str | None, day: str) -> dict[str, int]:
    with _LOCK:
        if tenant_id:
            tid = tenant_id.strip()
            return {
                "concurrent": _CONCURRENT.get(tid, 0),
                "daily_attempts": _ATTEMPTS.get(tid, {}).get(day, 0),
                "tenants_with_jobs": 1 if _CONCURRENT.get(tid, 0) > 0 else 0,
            }
        return {
            "concurrent": sum(_CONCURRENT.values()),
            "daily_attempts": sum(days.get(day, 0) for days in _ATTEMPTS.values()),
            "tenants_with_jobs": sum(1 for value in _CONCURRENT.values() if value > 0),
        }


def status(tenant_id: str | None = None) -> dict[str, int]:
    day = _day()
    tid = (tenant_id or "").strip()
    memory = _memory_status(tid or None, day)
    with _session() as session:
        if session is not None:
            from services.membership.processing_budgets_pg import (
                pg_attempt_used,
                pg_job_count,
                pg_tenants_with_jobs,
                table_ready,
            )

            if table_ready(session):
                if tid:
                    return {
                        "concurrent": pg_job_count(session, tenant_id=tid) + memory["concurrent"],
                        "concurrent_limit": DEFAULT_CONCURRENT_JOBS,
                        "daily_attempts": pg_attempt_used(session, tenant_id=tid, day_id=day)
                        + memory["daily_attempts"],
                        "daily_attempt_limit": DEFAULT_DAILY_PROVIDER_ATTEMPTS,
                        "import_item_limit": DEFAULT_IMPORT_ITEMS,
                    }
                return {
                    "concurrent": pg_job_count(session) + memory["concurrent"],
                    "concurrent_limit": DEFAULT_CONCURRENT_JOBS,
                    "daily_attempts": pg_attempt_used(session, day_id=day) + memory["daily_attempts"],
                    "daily_attempt_limit": DEFAULT_DAILY_PROVIDER_ATTEMPTS,
                    "import_item_limit": DEFAULT_IMPORT_ITEMS,
                    "tenants_with_jobs": pg_tenants_with_jobs(session) + memory["tenants_with_jobs"],
                }
    with _LOCK:
        job_count = len(_JOBS.get(tid) or []) if tid else sum(len(jobs) for jobs in _JOBS.values())
        job_tenants = sum(1 for jobs in _JOBS.values() if jobs)
    if tid:
        return {
            "concurrent": memory["concurrent"] or job_count,
            "concurrent_limit": DEFAULT_CONCURRENT_JOBS,
            "daily_attempts": memory["daily_attempts"],
            "daily_attempt_limit": DEFAULT_DAILY_PROVIDER_ATTEMPTS,
            "import_item_limit": DEFAULT_IMPORT_ITEMS,
        }
    return {
        "concurrent": memory["concurrent"] or job_count,
        "concurrent_limit": DEFAULT_CONCURRENT_JOBS,
        "daily_attempts": memory["daily_attempts"],
        "daily_attempt_limit": DEFAULT_DAILY_PROVIDER_ATTEMPTS,
        "import_item_limit": DEFAULT_IMPORT_ITEMS,
        "tenants_with_jobs": memory["tenants_with_jobs"] or job_tenants,
    }
