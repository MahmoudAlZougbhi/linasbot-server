"""Configurable daily AI Setup edit allowance. Default 30 accepted changes / UTC day.

Not a customer message charge. Fail closed when the store is unavailable.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from services.membership.message_catalog import AI_SETUP_DAILY_EDIT_DEFAULT

COUNTED_CM_SECTIONS = frozenset(
    {
        "ai_basics",
        "languages",
        "style",
        "dynamic_messages",
        "services",
        "branches",
        "opening_hours",
        "prices",
        "care",
        "knowledge",
        "faq",
        "handoff",
        "restricted",
        "actions",
        "comments",
        "ai_limits",
        "off_days",
        "requests_appointments",
    }
)

LIMIT_CODE = "AI_SETUP_DAILY_LIMIT"
POLICY_TIMEZONE = "UTC"

_LOCK = threading.Lock()
_USED: dict[str, dict[str, int]] = {}
_RESERVED: dict[str, dict[str, set[str]]] = {}
_COMMITTED: dict[str, dict[str, set[str]]] = {}
_OVERRIDES: dict[str, int] = {}
_BASELINE = AI_SETUP_DAILY_EDIT_DEFAULT


@dataclass(frozen=True)
class DailyEditDecision:
    allow: bool
    used: int
    reserved: int
    remaining: int
    limit: int
    window_id: str
    reset_at: str
    policy_version: str = "daily-edit-v1"
    source: str = "platform_baseline"
    reason: str = ""


class DailyEditLimitError(Exception):
    def __init__(self, decision: DailyEditDecision) -> None:
        super().__init__(LIMIT_CODE)
        self.decision = decision
        self.code = LIMIT_CODE


@contextmanager
def _ready_session(kind: str) -> Iterator[Any | None]:
    from services.membership.pg_store import memory_forced, optional_message_session

    if memory_forced():
        yield None
        return
    with optional_message_session() as session:
        if session is None:
            yield None
            return
        if kind == "policy":
            from services.membership.daily_edits_policy_pg import table_ready
        else:
            from services.membership.daily_edits_pg import table_ready
        yield session if table_ready(session) else None


def reset_daily_edits_for_tests() -> None:
    with _LOCK:
        _USED.clear()
        _RESERVED.clear()
        _COMMITTED.clear()
        _OVERRIDES.clear()
        global _BASELINE
        _BASELINE = AI_SETUP_DAILY_EDIT_DEFAULT


def set_platform_baseline(limit: int) -> None:
    if limit < 0:
        raise ValueError("daily edit limit cannot be negative")
    global _BASELINE
    with _LOCK:
        _BASELINE = limit
    with _ready_session("policy") as session:
        if session is not None:
            from services.membership.daily_edits_policy_pg import PLATFORM_TENANT, pg_upsert_limit

            pg_upsert_limit(session, tenant_id=PLATFORM_TENANT, limit_value=limit, source="platform_baseline")


def set_tenant_override(tenant_id: str, limit: int | None) -> None:
    tid = tenant_id.strip()
    with _LOCK:
        if limit is None:
            _OVERRIDES.pop(tid, None)
        elif limit < 0:
            raise ValueError("daily edit limit cannot be negative")
        else:
            _OVERRIDES[tid] = limit
    with _ready_session("policy") as session:
        if session is None:
            return
        from services.membership.daily_edits_policy_pg import pg_delete_limit, pg_upsert_limit

        if limit is None:
            pg_delete_limit(session, tid)
        else:
            pg_upsert_limit(session, tenant_id=tid, limit_value=limit, source="tenant_override")


def _window(now: datetime | None = None) -> tuple[str, str]:
    current = now or datetime.now(UTC)
    start = current.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    reset = start + timedelta(days=1)
    return start.date().isoformat(), reset.isoformat()


def effective_limit(tenant_id: str) -> tuple[int, str]:
    tid = tenant_id.strip()
    with _ready_session("policy") as session:
        if session is not None:
            from services.membership.daily_edits_policy_pg import pg_load_limits

            baseline, overrides = pg_load_limits(session)
            if tid in overrides:
                return overrides[tid], "tenant_override"
            if baseline is not None:
                return baseline, "platform_baseline"
    with _LOCK:
        if tid in _OVERRIDES:
            return _OVERRIDES[tid], "tenant_override"
        return _BASELINE, "platform_baseline"


def _counts(tenant_id: str, window_id: str) -> tuple[int, int]:
    used = _USED.get(tenant_id, {}).get(window_id, 0)
    reserved = len(_RESERVED.get(tenant_id, {}).get(window_id, set()))
    return used, reserved


def _memory_has(tenant_id: str, window_id: str, operation_id: str) -> bool:
    with _LOCK:
        reserved_ids = _RESERVED.get(tenant_id, {}).get(window_id, set())
        committed_ids = _COMMITTED.get(tenant_id, {}).get(window_id, set())
        return operation_id in reserved_ids or operation_id in committed_ids


def _memory_extras(tenant_id: str, window_id: str, sql_ids: set[str]) -> tuple[int, int]:
    with _LOCK:
        reserved_ids = set(_RESERVED.get(tenant_id, {}).get(window_id, set()))
        committed_ids = set(_COMMITTED.get(tenant_id, {}).get(window_id, set()))
    return len(committed_ids - sql_ids), len(reserved_ids - sql_ids)


def _sync_memory(tenant_id: str, window_id: str, operation_id: str, action: str) -> None:
    with _LOCK:
        reserved_ids = _RESERVED.setdefault(tenant_id, {}).setdefault(window_id, set())
        committed_ids = _COMMITTED.setdefault(tenant_id, {}).setdefault(window_id, set())
        if action == "reserved":
            reserved_ids.add(operation_id)
        elif action == "committed":
            reserved_ids.discard(operation_id)
            committed_ids.add(operation_id)
        elif action == "released":
            reserved_ids.discard(operation_id)


def _combined_decision(
    *,
    tid: str,
    window_id: str,
    reset_at: str,
    limit: int,
    source: str,
    used: int,
    reserved: int,
    sql_ids: set[str],
    allow: bool = True,
    reason: str = "",
) -> DailyEditDecision:
    extra_used, extra_reserved = _memory_extras(tid, window_id, sql_ids)
    used += extra_used
    reserved += extra_reserved
    remaining = max(0, limit - used - reserved)
    return DailyEditDecision(
        allow=allow if reason else remaining > 0 or limit > 0 and used + reserved < limit,
        used=used,
        reserved=reserved,
        remaining=remaining,
        limit=limit,
        window_id=window_id,
        reset_at=reset_at,
        source=source,
        reason=reason,
    )


def status(tenant_id: str, *, now: datetime | None = None) -> DailyEditDecision:
    tid = tenant_id.strip()
    window_id, reset_at = _window(now)
    limit, source = effective_limit(tid)
    with _ready_session("edits") as session:
        if session is not None:
            from services.membership.daily_edits_pg import pg_counts, pg_operation_ids

            used, reserved = pg_counts(session, tid, window_id)
            sql_ids = set(pg_operation_ids(session, tid, window_id))
            return _combined_decision(
                tid=tid,
                window_id=window_id,
                reset_at=reset_at,
                limit=limit,
                source=source,
                used=used,
                reserved=reserved,
                sql_ids=sql_ids,
            )
    with _LOCK:
        used, reserved = _counts(tid, window_id)
    remaining = max(0, limit - used - reserved)
    return DailyEditDecision(
        allow=remaining > 0 or limit > 0 and used + reserved < limit,
        used=used,
        reserved=reserved,
        remaining=remaining,
        limit=limit,
        window_id=window_id,
        reset_at=reset_at,
        source=source,
    )


def known_daily_edit_tenant_ids() -> list[str]:
    """Tenants already present on edit rows or overrides. Do not invent ids."""
    window_id, _ = _window()
    ids: set[str] = set()
    with _ready_session("edits") as session:
        if session is not None:
            from services.membership.daily_edits_pg import pg_tenant_ids

            ids.update(pg_tenant_ids(session, window_id=window_id))
    with _ready_session("policy") as session:
        if session is not None:
            from services.membership.daily_edits_policy_pg import PLATFORM_TENANT, pg_load_limits

            _baseline, overrides = pg_load_limits(session)
            ids.update(overrides)
            ids.discard(PLATFORM_TENANT)
    with _LOCK:
        ids.update(tid for tid, windows in _USED.items() if windows.get(window_id))
        ids.update(tid for tid, windows in _RESERVED.items() if windows.get(window_id))
        ids.update(tid for tid, windows in _COMMITTED.items() if windows.get(window_id))
        ids.update(_OVERRIDES)
    ids.discard("")
    return sorted(ids)


def operation_id(*, tenant_id: str, kind: str, payload_hash: str) -> str:
    raw = f"{tenant_id}|{kind}|{payload_hash}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:32]


def payload_hash(payload: object) -> str:
    return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()


def reserve_edit(
    *,
    tenant_id: str,
    operation_id: str,
    now: datetime | None = None,
) -> DailyEditDecision:
    tid = tenant_id.strip()
    window_id, reset_at = _window(now)
    limit, source = effective_limit(tid)
    with _ready_session("edits") as session:
        if session is not None:
            from services.membership.daily_edits_pg import pg_counts, pg_operation_ids, pg_reserve

            sql_ids = set(pg_operation_ids(session, tid, window_id))
            used, reserved = pg_counts(session, tid, window_id)
            extra_used, extra_reserved = _memory_extras(tid, window_id, sql_ids)
            if operation_id in sql_ids or _memory_has(tid, window_id, operation_id):
                return _combined_decision(
                    tid=tid,
                    window_id=window_id,
                    reset_at=reset_at,
                    limit=limit,
                    source=source,
                    used=used,
                    reserved=reserved,
                    sql_ids=sql_ids,
                )
            if used + reserved + extra_used + extra_reserved >= limit:
                raise DailyEditLimitError(
                    _combined_decision(
                        tid=tid,
                        window_id=window_id,
                        reset_at=reset_at,
                        limit=limit,
                        source=source,
                        used=used,
                        reserved=reserved,
                        sql_ids=sql_ids,
                        allow=False,
                        reason=LIMIT_CODE,
                    )
                )
            decision = pg_reserve(
                session,
                tenant_id=tid,
                operation_id=operation_id,
                window_id=window_id,
                reset_at=reset_at,
            )
            _sync_memory(tid, window_id, operation_id, "reserved")
            sql_ids.add(operation_id)
            return _combined_decision(
                tid=tid,
                window_id=window_id,
                reset_at=reset_at,
                limit=limit,
                source=source,
                used=decision.used,
                reserved=decision.reserved,
                sql_ids=sql_ids,
            )
    with _LOCK:
        used_map = _USED.setdefault(tid, {})
        reserved_ids = _RESERVED.setdefault(tid, {}).setdefault(window_id, set())
        committed_ids = _COMMITTED.setdefault(tid, {}).setdefault(window_id, set())
        used_count = used_map.get(window_id, 0)
        if operation_id in reserved_ids or operation_id in committed_ids:
            remaining = max(0, limit - used_count - len(reserved_ids))
            return DailyEditDecision(
                True, used_count, len(reserved_ids), remaining, limit, window_id, reset_at, source=source
            )
        if used_count + len(reserved_ids) >= limit:
            decision = DailyEditDecision(
                False,
                used_count,
                len(reserved_ids),
                0,
                limit,
                window_id,
                reset_at,
                source=source,
                reason=LIMIT_CODE,
            )
            raise DailyEditLimitError(decision)
        reserved_ids.add(operation_id)
        remaining = max(0, limit - used_count - len(reserved_ids))
        return DailyEditDecision(
            True, used_count, len(reserved_ids), remaining, limit, window_id, reset_at, source=source
        )


def commit_edit(*, tenant_id: str, operation_id: str, now: datetime | None = None) -> DailyEditDecision:
    tid = tenant_id.strip()
    window_id, reset_at = _window(now)
    limit, source = effective_limit(tid)
    with _ready_session("edits") as session:
        if session is not None:
            from services.membership.daily_edits_pg import pg_commit, pg_operation_ids

            decision = pg_commit(
                session,
                tenant_id=tid,
                operation_id=operation_id,
                window_id=window_id,
                reset_at=reset_at,
            )
            _sync_memory(tid, window_id, operation_id, "committed")
            return _combined_decision(
                tid=tid,
                window_id=window_id,
                reset_at=reset_at,
                limit=limit,
                source=source,
                used=decision.used,
                reserved=decision.reserved,
                sql_ids=set(pg_operation_ids(session, tid, window_id)),
            )
    with _LOCK:
        reserved_ids = _RESERVED.setdefault(tid, {}).setdefault(window_id, set())
        committed_ids = _COMMITTED.setdefault(tid, {}).setdefault(window_id, set())
        if operation_id in committed_ids:
            used_count = _USED.get(tid, {}).get(window_id, 0)
            remaining = max(0, limit - used_count - len(reserved_ids))
            return DailyEditDecision(
                True, used_count, len(reserved_ids), remaining, limit, window_id, reset_at, source=source
            )
        reserved_ids.discard(operation_id)
        used = _USED.setdefault(tid, {})
        used[window_id] = used.get(window_id, 0) + 1
        committed_ids.add(operation_id)
        used_count = used[window_id]
        remaining = max(0, limit - used_count - len(reserved_ids))
        return DailyEditDecision(
            True, used_count, len(reserved_ids), remaining, limit, window_id, reset_at, source=source
        )


def release_edit(*, tenant_id: str, operation_id: str, now: datetime | None = None) -> DailyEditDecision:
    tid = tenant_id.strip()
    window_id, reset_at = _window(now)
    limit, source = effective_limit(tid)
    with _ready_session("edits") as session:
        if session is not None:
            from services.membership.daily_edits_pg import pg_operation_ids, pg_release

            decision = pg_release(
                session,
                tenant_id=tid,
                operation_id=operation_id,
                window_id=window_id,
                reset_at=reset_at,
            )
            _sync_memory(tid, window_id, operation_id, "released")
            return _combined_decision(
                tid=tid,
                window_id=window_id,
                reset_at=reset_at,
                limit=limit,
                source=source,
                used=decision.used,
                reserved=decision.reserved,
                sql_ids=set(pg_operation_ids(session, tid, window_id)),
            )
    with _LOCK:
        reserved_ids = _RESERVED.setdefault(tid, {}).setdefault(window_id, set())
        reserved_ids.discard(operation_id)
        used_count = _USED.get(tid, {}).get(window_id, 0)
        remaining = max(0, limit - used_count - len(reserved_ids))
        return DailyEditDecision(
            True, used_count, len(reserved_ids), remaining, limit, window_id, reset_at, source=source
        )


def reserve_cm_section(*, tenant_id: str, section: str, payload: object) -> str | None:
    if section not in COUNTED_CM_SECTIONS:
        return None
    op = operation_id(tenant_id=tenant_id, kind=f"cm:{section}", payload_hash=payload_hash(payload))
    reserve_edit(tenant_id=tenant_id, operation_id=op)
    return op


def decision_payload(decision: DailyEditDecision) -> dict[str, Any]:
    return {
        "code": LIMIT_CODE if not decision.allow else "ok",
        "limit": decision.limit,
        "used": decision.used,
        "reserved": decision.reserved,
        "remaining": decision.remaining,
        "window_id": decision.window_id,
        "reset_at": decision.reset_at,
        "policy_version": decision.policy_version,
        "source": decision.source,
        "timezone": POLICY_TIMEZONE,
    }
