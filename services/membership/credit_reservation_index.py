"""Bounded leftover-credit reservation index. No guessed tenants, no full-balance scan."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from storage.persistent_storage import _DATA_ROOT

_LOCK = threading.Lock()
_ITEMS: dict[str, OpenCreditReservation] = {}
_HYDRATED = False


@dataclass
class OpenCreditReservation:
    reservation_id: str
    tenant_id: str
    request_id: str
    operation_type: str
    created_at: str
    state: str = "reserved"


def reset_credit_reservation_index_for_tests() -> None:
    global _HYDRATED
    with _LOCK:
        _ITEMS.clear()
        _HYDRATED = True
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.credit_reservation_index_pg import pg_reset, table_ready

        if table_ready(session):
            pg_reset(session)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _root() -> Path:
    path = Path(_DATA_ROOT) / "credit_reservation_index"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _memory_forced() -> bool:
    from services.membership.pg_store import memory_forced

    return memory_forced()


def _hydrate() -> None:
    global _HYDRATED
    if _HYDRATED or _memory_forced():
        return
    loaded: dict[str, OpenCreditReservation] = {}
    sql_known: set[str] = set()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.membership.credit_reservation_index_pg import (
                pg_list,
                pg_reservation_ids,
                table_ready,
            )

            if table_ready(session):
                for state in ("reserved", "pending_settlement"):
                    for item in pg_list(session, state=state):
                        loaded[item.reservation_id] = item
                sql_known.update(pg_reservation_ids(session))
    for path in _root().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            rid = str(data.get("reservation_id") or path.stem)
            if rid in loaded or rid in sql_known:
                continue
            loaded[rid] = OpenCreditReservation(
                reservation_id=rid,
                tenant_id=str(data.get("tenant_id") or ""),
                request_id=str(data.get("request_id") or ""),
                operation_type=str(data.get("operation_type") or ""),
                created_at=str(data.get("created_at") or _now()),
                state=str(data.get("state") or "reserved"),
            )
        except Exception:
            continue
    with _LOCK:
        if not _HYDRATED:
            _ITEMS.update(loaded)
            _HYDRATED = True
    _promote_missing_to_pg()


def _promote_missing_to_pg() -> None:
    if _memory_forced() or not _ITEMS:
        return
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.credit_reservation_index_pg import pg_get, pg_upsert, table_ready

        if not table_ready(session):
            return
        with _LOCK:
            items = list(_ITEMS.values())
        for item in items:
            if pg_get(session, item.reservation_id) is None:
                pg_upsert(session, item)


def _persist(item: OpenCreditReservation) -> None:
    if _memory_forced():
        return
    try:
        (_root() / f"{item.reservation_id}.json").write_text(
            json.dumps(asdict(item), ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass
    _persist_pg(item)


def _persist_pg(item: OpenCreditReservation) -> None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.credit_reservation_index_pg import pg_upsert, table_ready

        if table_ready(session):
            pg_upsert(session, item)


def _get(reservation_id: str) -> OpenCreditReservation | None:
    if not _memory_forced():
        from services.membership.pg_store import optional_message_session

        with optional_message_session() as session:
            if session is not None:
                from services.membership.credit_reservation_index_pg import pg_get, table_ready

                if table_ready(session):
                    found = pg_get(session, reservation_id)
                    if found is not None:
                        with _LOCK:
                            _ITEMS[reservation_id] = found
                        return found
                    return None
    with _LOCK:
        return _ITEMS.get(reservation_id)


def _list_pg(*, tenant_id: str = "", state: str = "reserved") -> list[OpenCreditReservation] | None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return None
        from services.membership.credit_reservation_index_pg import pg_list, table_ready

        if not table_ready(session):
            return None
        return pg_list(session, tenant_id=tenant_id, state=state)


def _sql_known_ids(*, tenant_id: str = "") -> set[str]:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return set()
        from services.membership.credit_reservation_index_pg import pg_reservation_ids, table_ready

        if not table_ready(session):
            return set()
        return pg_reservation_ids(session, tenant_id=tenant_id)


def record_open(
    *,
    tenant_id: str,
    reservation_id: str,
    request_id: str,
    operation_type: str,
    created_at: str = "",
) -> OpenCreditReservation | None:
    if not tenant_id or not reservation_id:
        return None
    _hydrate()
    existing = _get(reservation_id)
    if existing is not None and existing.state in {"reserved", "pending_settlement"}:
        return existing
    item = OpenCreditReservation(
        reservation_id=reservation_id,
        tenant_id=tenant_id,
        request_id=request_id or reservation_id,
        operation_type=operation_type,
        created_at=created_at or (existing.created_at if existing is not None else _now()),
        state="reserved",
    )
    with _LOCK:
        current = _ITEMS.get(reservation_id)
        if current is not None and current.state in {"reserved", "pending_settlement"}:
            _persist(current)
            return current
        _ITEMS[reservation_id] = item
        _persist(item)
        return item


def seed_from_pending_settlements(*, limit: int = 200) -> int:
    """Index leftover holds that already have a settlement row. No tenant guess."""
    from services.membership.pending_settlement import list_pending

    seeded = 0
    after = ""
    cap = max(1, min(int(limit), 200))
    while True:
        batch = list_pending(states=("reserved",), limit=cap, after_id=after)
        if not batch:
            break
        for item in batch:
            if item.billing_policy != "legacy_credits" or not item.reservation_id:
                continue
            record_open(
                tenant_id=item.tenant_id,
                reservation_id=item.reservation_id,
                request_id=item.operation_id or item.reservation_id,
                operation_type=str((item.extra or {}).get("operation_type") or item.channel or "legacy_credits"),
                created_at=item.created_at,
            )
            seeded += 1
        after = batch[-1].settlement_id
        if len(batch) < cap:
            break
    return seeded


def known_index_tenant_ids() -> list[str]:
    """Tenants already present on leftover-index rows. Do not invent ids."""
    _hydrate()
    with _LOCK:
        ids = {item.tenant_id for item in _ITEMS.values() if item.tenant_id}
    if not _memory_forced():
        from services.membership.pg_store import optional_message_session

        with optional_message_session() as session:
            if session is not None:
                from services.membership.credit_reservation_index_pg import pg_tenant_ids, table_ready

                if table_ready(session):
                    ids.update(pg_tenant_ids(session))
    return sorted(ids)


def mark_closed(reservation_id: str, *, state: str = "settled") -> None:
    if not reservation_id:
        return
    _hydrate()
    with _LOCK:
        item = _ITEMS.get(reservation_id)
        if item is not None:
            item.state = state
    if _memory_forced():
        return
    try:
        (_root() / f"{reservation_id}.json").unlink(missing_ok=True)
    except Exception:
        pass
    if item is not None:
        _persist_pg(item)
        return
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.credit_reservation_index_pg import pg_get, pg_upsert, table_ready

        if not table_ready(session):
            return
        found = pg_get(session, reservation_id)
        if found is not None:
            found.state = state
            pg_upsert(session, found)


def open_counts(*, tenant_id: str = "", stale_after_seconds: int = 3600) -> dict[str, int]:
    """Bounded open leftover-credit holds. Stale count is paginated, not a tenant guess."""
    tid = tenant_id.strip()
    _hydrate()
    rows: list[OpenCreditReservation] = []
    seen: set[str] = set()
    pg_rows = _list_pg(tenant_id=tid, state="reserved")
    if pg_rows is not None:
        rows.extend(pg_rows)
        seen.update(item.reservation_id for item in pg_rows)
        seen.update(_sql_known_ids(tenant_id=tid))
    with _LOCK:
        for item in _ITEMS.values():
            if item.state != "reserved" or item.reservation_id in seen:
                continue
            if tid and item.tenant_id != tid:
                continue
            rows.append(item)
            seen.add(item.reservation_id)
    stale = list_stale_open(older_than_seconds=stale_after_seconds, limit=200)
    if tid:
        stale = [item for item in stale if item.tenant_id == tid]
    return {"open": len(rows), "stale": len(stale)}


def list_stale_open(
    *, older_than_seconds: int = 3600, limit: int = 50, after_id: str = ""
) -> list[OpenCreditReservation]:
    cap = max(1, min(int(limit), 200))
    cutoff = datetime.now(UTC).timestamp() - max(1, int(older_than_seconds))
    _hydrate()
    rows: list[OpenCreditReservation] = []
    seen: set[str] = set()
    pg_rows = _list_pg(state="reserved")
    if pg_rows is not None:
        rows.extend(pg_rows)
        seen.update(item.reservation_id for item in pg_rows)
        seen.update(_sql_known_ids())
    with _LOCK:
        for item in _ITEMS.values():
            if item.state != "reserved" or item.reservation_id in seen:
                continue
            rows.append(item)
            seen.add(item.reservation_id)
    if after_id:
        rows = [item for item in rows if item.reservation_id > after_id]
    stale: list[OpenCreditReservation] = []
    for item in sorted(rows, key=lambda row: row.reservation_id):
        try:
            parsed = datetime.fromisoformat(item.created_at.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            if parsed.timestamp() > cutoff:
                continue
        except ValueError:
            continue
        stale.append(item)
        if len(stale) >= cap:
            break
    return stale
