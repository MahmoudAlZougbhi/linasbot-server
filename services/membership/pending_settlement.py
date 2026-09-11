"""Durable pending-settlement registry. Paginated; no guessed tenant scan."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from storage.persistent_storage import _DATA_ROOT

BillingPolicy = Literal["legacy_credits", "message_units"]
SettlementState = Literal["reserved", "pending_settlement", "settled", "released", "unresolved"]

_LOCK = threading.Lock()
_ITEMS: dict[str, PendingSettlement] = {}
_HYDRATED = False
MAX_ATTEMPTS = 8


@dataclass
class PendingSettlement:
    settlement_id: str
    tenant_id: str
    reservation_id: str
    operation_id: str
    billing_policy: BillingPolicy
    state: SettlementState
    created_at: str
    updated_at: str
    attempts: int = 0
    send_status: str = ""
    provider_message_id: str = ""
    channel: str = ""
    reason: str = ""
    extra: dict[str, Any] = field(default_factory=dict)


def reset_pending_settlements_for_tests() -> None:
    global _HYDRATED
    with _LOCK:
        _ITEMS.clear()
        _HYDRATED = True
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.pending_settlement_pg import pg_reset, table_ready

        if table_ready(session):
            pg_reset(session)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _root() -> Path:
    path = Path(_DATA_ROOT) / "pending_settlements"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _memory_forced() -> bool:
    from services.membership.pg_store import memory_forced

    return memory_forced()


def _hydrate() -> None:
    global _HYDRATED
    if _HYDRATED or _memory_forced():
        return
    loaded: dict[str, PendingSettlement] = {}
    sql_known: set[str] = set()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.membership.pending_settlement_pg import pg_list, pg_settlement_ids, table_ready

            if table_ready(session):
                for item in pg_list(
                    session,
                    states=("reserved", "pending_settlement", "settled", "released", "unresolved"),
                    limit=2000,
                ):
                    loaded[item.settlement_id] = item
                sql_known.update(pg_settlement_ids(session))
    for path in _root().glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            sid = str(data.get("settlement_id") or path.stem)
            if sid in loaded or sid in sql_known:
                continue
            loaded[sid] = PendingSettlement(
                settlement_id=sid,
                tenant_id=str(data.get("tenant_id") or ""),
                reservation_id=str(data.get("reservation_id") or ""),
                operation_id=str(data.get("operation_id") or ""),
                billing_policy=data.get("billing_policy") or "legacy_credits",
                state=data.get("state") or "reserved",
                created_at=str(data.get("created_at") or _now()),
                updated_at=str(data.get("updated_at") or _now()),
                attempts=int(data.get("attempts") or 0),
                send_status=str(data.get("send_status") or ""),
                provider_message_id=str(data.get("provider_message_id") or ""),
                channel=str(data.get("channel") or ""),
                reason=str(data.get("reason") or ""),
                extra=dict(data.get("extra") or {}),
            )
        except Exception:
            continue
    with _LOCK:
        if not _HYDRATED:
            _ITEMS.update(loaded)
            _HYDRATED = True


def _key(tenant_id: str, reservation_id: str, operation_id: str) -> str:
    return f"{tenant_id}:{reservation_id or operation_id}"


def record_hold(
    *,
    tenant_id: str,
    reservation_id: str,
    operation_id: str,
    billing_policy: BillingPolicy,
    channel: str = "",
    extra: dict[str, Any] | None = None,
) -> PendingSettlement:
    return upsert(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        operation_id=operation_id,
        billing_policy=billing_policy,
        state="reserved",
        channel=channel,
        extra=extra,
    )


def record_pending_after_send(
    *,
    tenant_id: str,
    reservation_id: str,
    operation_id: str,
    billing_policy: BillingPolicy,
    provider_message_id: str = "",
    channel: str = "",
    reason: str = "capture_failed_after_send",
) -> PendingSettlement:
    return upsert(
        tenant_id=tenant_id,
        reservation_id=reservation_id,
        operation_id=operation_id,
        billing_policy=billing_policy,
        state="pending_settlement",
        send_status="sent",
        provider_message_id=provider_message_id,
        channel=channel,
        reason=reason,
    )


def _sql_ready() -> bool:
    if _memory_forced():
        return False
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return False
        from services.membership.pending_settlement_pg import table_ready

        return table_ready(session)


def _get(sid: str) -> PendingSettlement | None:
    if not _memory_forced():
        from services.membership.pg_store import optional_message_session

        with optional_message_session() as session:
            if session is not None:
                from services.membership.pending_settlement_pg import pg_get, table_ready

                if table_ready(session):
                    found = pg_get(session, sid)
                    if found is not None:
                        with _LOCK:
                            _ITEMS[sid] = found
                        return found
    with _LOCK:
        return _ITEMS.get(sid)


def _merge_extra(current: dict[str, Any] | None, incoming: dict[str, Any] | None) -> dict[str, Any]:
    prior = dict(current or {})
    extra = dict(incoming or {})
    merged = {**prior, **extra}
    seen: list[str] = []
    for value in (
        *(prior.get("candidate_ids") or prior.get("aliases") or []),
        *(extra.get("candidate_ids") or extra.get("aliases") or []),
    ):
        text = str(value or "").strip()
        if text and text not in seen:
            seen.append(text)
    if seen:
        merged["candidate_ids"] = seen
    return merged


def upsert(
    *,
    tenant_id: str,
    reservation_id: str,
    operation_id: str,
    billing_policy: BillingPolicy,
    state: SettlementState,
    send_status: str = "",
    provider_message_id: str = "",
    channel: str = "",
    reason: str = "",
    extra: dict[str, Any] | None = None,
) -> PendingSettlement:
    _hydrate()
    sid = _key(tenant_id, reservation_id, operation_id)
    stamp = _now()
    current = _get(sid)
    with _LOCK:
        item = PendingSettlement(
            settlement_id=sid,
            tenant_id=tenant_id,
            reservation_id=reservation_id,
            operation_id=operation_id,
            billing_policy=current.billing_policy if current else billing_policy,
            state=state,
            created_at=current.created_at if current else stamp,
            updated_at=stamp,
            attempts=current.attempts if current else 0,
            send_status=send_status or (current.send_status if current else ""),
            provider_message_id=provider_message_id or (current.provider_message_id if current else ""),
            channel=channel or (current.channel if current else ""),
            reason=reason or (current.reason if current else ""),
            extra=_merge_extra(current.extra if current else {}, extra),
        )
        if current and current.billing_policy != billing_policy:
            item.extra["policy_pin"] = current.billing_policy
        _ITEMS[sid] = item
        if not _memory_forced():
            (_root() / f"{sid.replace(':', '_')}.json").write_text(
                json.dumps(asdict(item), ensure_ascii=False),
                encoding="utf-8",
            )
    _persist_pg(item)
    return item


def bump_attempt(settlement_id: str, *, reason: str = "") -> PendingSettlement | None:
    _hydrate()
    item = _get(settlement_id)
    with _LOCK:
        if item is None:
            return None
        item.attempts += 1
        item.updated_at = _now()
        if reason:
            item.reason = reason
        if item.attempts >= MAX_ATTEMPTS and item.state == "pending_settlement":
            item.state = "unresolved"
        updated = item
    _persist_pg(updated)
    return updated


def _persist_pg(item: PendingSettlement) -> None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return
        from services.membership.pending_settlement_pg import pg_upsert, table_ready

        if table_ready(session):
            pg_upsert(session, item)


def _list_pg(
    *,
    states: tuple[SettlementState, ...],
    limit: int,
    after_id: str,
    tenant_id: str,
) -> list[PendingSettlement] | None:
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return None
        from services.membership.pending_settlement_pg import pg_list, table_ready

        if not table_ready(session):
            return None
        return pg_list(session, states=states, limit=limit, after_id=after_id, tenant_id=tenant_id)


def _sql_known_ids(*, tenant_id: str = "") -> set[str]:
    try:
        from services.membership.pg_store import optional_message_session

        with optional_message_session() as session:
            if session is None:
                return set()
            from services.membership.pending_settlement_pg import pg_settlement_ids, table_ready

            if not table_ready(session):
                return set()
            return pg_settlement_ids(session, tenant_id=tenant_id)
    except Exception:
        return set()


def list_pending(
    *,
    states: tuple[SettlementState, ...] = ("pending_settlement", "unresolved", "reserved"),
    limit: int = 50,
    after_id: str = "",
    tenant_id: str = "",
) -> list[PendingSettlement]:
    cap = max(1, min(int(limit), 200))
    tid = tenant_id.strip()
    rows: list[PendingSettlement] = []
    seen: set[str] = set()
    pg_rows = _list_pg(states=states, limit=cap, after_id=after_id, tenant_id=tid)
    if pg_rows is not None:
        rows.extend(pg_rows)
        seen.update(item.settlement_id for item in pg_rows)
        seen.update(_sql_known_ids(tenant_id=tid))
    _hydrate()
    with _LOCK:
        for item in _ITEMS.values():
            if item.state not in states:
                continue
            if tid and item.tenant_id != tid:
                continue
            if item.settlement_id in seen:
                continue
            rows.append(item)
            seen.add(item.settlement_id)
    rows.sort(key=lambda item: item.settlement_id)
    if after_id:
        rows = [item for item in rows if item.settlement_id > after_id]
    return rows[:cap]


def _aliases(item: PendingSettlement) -> set[str]:
    aliases = {str(item.reservation_id or "").strip(), str(item.operation_id or "").strip()}
    extras = item.extra.get("candidate_ids") or item.extra.get("aliases") or []
    aliases.update(str(alias or "").strip() for alias in extras)
    aliases.discard("")
    return aliases


def get_pending(tenant_id: str, reservation_id: str, operation_id: str = "") -> PendingSettlement | None:
    if not tenant_id or not (reservation_id or operation_id):
        return None
    _hydrate()
    sid = _key(tenant_id, reservation_id, operation_id or reservation_id)
    found = _get(sid)
    if found is not None:
        return found
    wanted = {str(reservation_id or "").strip(), str(operation_id or "").strip()}
    wanted.discard("")
    with _LOCK:
        for item in _ITEMS.values():
            if item.tenant_id == tenant_id and (_aliases(item) & wanted):
                return item
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is None:
            return None
        from services.membership.pending_settlement_pg import pg_get_by_alias, pg_get_by_reservation, table_ready

        if not table_ready(session):
            return None
        return pg_get_by_reservation(session, tenant_id, reservation_id) or pg_get_by_alias(
            session, tenant_id, wanted
        )


def policy_for_operation(tenant_id: str, *operation_ids: str) -> BillingPolicy | None:
    wanted = {str(item or "").strip() for item in operation_ids if str(item or "").strip()}
    if not wanted:
        return None
    if not _memory_forced():
        from services.membership.pg_store import optional_message_session

        with optional_message_session() as session:
            if session is not None:
                from services.membership.pending_settlement_pg import pg_policy_for, table_ready

                if table_ready(session):
                    found = pg_policy_for(session, tenant_id, wanted)
                    return found if found in {"legacy_credits", "message_units"} else None
    _hydrate()
    with _LOCK:
        for item in _ITEMS.values():
            if item.tenant_id != tenant_id:
                continue
            if item.state not in {"reserved", "pending_settlement"}:
                continue
            aliases = {str(alias or "").strip() for alias in (item.extra.get("candidate_ids") or [])}
            if item.operation_id in wanted or item.reservation_id in wanted or (wanted & aliases):
                return item.billing_policy
    return None


def known_settlement_tenant_ids() -> list[str]:
    """Tenants already present on settlement rows. Do not invent ids."""
    ids: set[str] = set()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.membership.pending_settlement_pg import pg_tenant_ids, table_ready

            if table_ready(session):
                ids.update(pg_tenant_ids(session))
    _hydrate()
    with _LOCK:
        ids.update(item.tenant_id for item in _ITEMS.values() if item.tenant_id)
    return sorted(ids)


def pending_counts(*, tenant_id: str = "") -> dict[str, int]:
    tid = tenant_id.strip()
    counts = {"reserved": 0, "pending_settlement": 0, "settled": 0, "released": 0, "unresolved": 0}
    seen: set[str] = set()
    from services.membership.pg_store import optional_message_session

    with optional_message_session() as session:
        if session is not None:
            from services.membership.pending_settlement_pg import pg_counts, pg_settlement_ids, table_ready

            if table_ready(session):
                counts.update(pg_counts(session, tenant_id=tid))
                seen.update(pg_settlement_ids(session, tenant_id=tid))
    _hydrate()
    with _LOCK:
        for item in _ITEMS.values():
            if item.settlement_id in seen:
                continue
            if tid and item.tenant_id != tid:
                continue
            counts[item.state] = counts.get(item.state, 0) + 1
    return counts
