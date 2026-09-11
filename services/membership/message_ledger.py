"""In-process message entitlement ledger. SQL tables are the durable target.

Live Customer AI keeps the credit gate until MESSAGE_BILLING_ENABLED.
Quantities are non-negative integer message units. Money is not stored here.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from services.membership.lot_window import lot_is_live
from services.membership.message_policy import ResponseClass, message_units_for


def _live_remaining(lot: MessageLot) -> int:
    return lot.remaining if lot_is_live(lot) else 0

_LOCK = threading.Lock()


@dataclass
class MessageLot:
    lot_id: str
    tenant_id: str
    kind: str
    period_id: str
    granted: int
    remaining: int
    expires: bool = True
    catalog_version: str = ""


@dataclass
class MessageReservation:
    reservation_id: str
    tenant_id: str
    operation_id: str
    units: int
    status: str
    lot_id: str = ""
    period_id: str = ""
    response_class: str = ""
    created_at: str = ""


@dataclass
class LedgerSnapshot:
    tenant_id: str
    included: int = 0
    purchased: int = 0
    reserved: int = 0
    remaining: int = 0
    lots: list[MessageLot] = field(default_factory=list)


class InsufficientMessages(Exception):
    def __init__(self, tenant_id: str, remaining: int) -> None:
        super().__init__(f"insufficient_messages tenant={tenant_id} remaining={remaining}")
        self.tenant_id = tenant_id
        self.remaining = remaining


class ReservationConflict(Exception):
    pass


_LOTS: dict[str, list[MessageLot]] = {}
_RESERVATIONS: dict[str, MessageReservation] = {}


def reset_ledger_for_tests() -> None:
    with _LOCK:
        _LOTS.clear()
        _RESERVATIONS.clear()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _res_key(tenant_id: str, operation_id: str) -> str:
    return f"{tenant_id}:{operation_id}"


def _pg_session():
    from services.membership.message_flags import message_billing_enabled
    from services.membership.pg_store import optional_message_session, postgres_requested

    require = message_billing_enabled() and postgres_requested()
    return optional_message_session(require=require)


def grant_lot(
    *,
    tenant_id: str,
    lot_id: str,
    kind: str,
    period_id: str,
    amount: int,
    expires: bool = True,
    catalog_version: str = "",
) -> MessageLot:
    if amount < 0:
        raise ValueError("grant amount must be non-negative")
    tid = tenant_id.strip()
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_grant_lot

            return pg_grant_lot(
                session,
                tenant_id=tid,
                lot_id=lot_id,
                kind=kind,
                period_id=period_id,
                amount=amount,
                expires=expires,
                catalog_version=catalog_version,
            )
    with _LOCK:
        existing = next((lot for lot in _LOTS.get(tid, []) if lot.lot_id == lot_id), None)
        if existing is not None:
            return existing
        lot = MessageLot(
            lot_id=lot_id,
            tenant_id=tid,
            kind=kind,
            period_id=period_id,
            granted=amount,
            remaining=amount,
            expires=expires,
            catalog_version=catalog_version,
        )
        _LOTS.setdefault(tid, []).append(lot)
        return lot


def snapshot(tenant_id: str) -> LedgerSnapshot:
    tid = tenant_id.strip()
    lots: list[MessageLot] = []
    seen: set[str] = set()
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_snapshot

            sql = pg_snapshot(session, tid)
            lots.extend(sql.lots)
            seen.update(lot.lot_id for lot in sql.lots)
    with _LOCK:
        for lot in _LOTS.get(tid, []):
            if lot.lot_id in seen:
                continue
            lots.append(lot)
            seen.add(lot.lot_id)
    reserved = sum(item.units for item in list_reservations(tid) if item.status == "reserved")
    included = sum(_live_remaining(lot) for lot in lots if lot.kind == "included")
    purchased = sum(_live_remaining(lot) for lot in lots if lot.kind != "included")
    return LedgerSnapshot(
        tenant_id=tid,
        included=included,
        purchased=purchased,
        reserved=reserved,
        remaining=max(0, included + purchased - reserved),
        lots=lots,
    )


def remaining_messages(tenant_id: str) -> int:
    return snapshot(tenant_id).remaining


def grant_purchased(
    *,
    tenant_id: str,
    lot_id: str,
    amount: int,
    source_transaction_id: str,
) -> MessageLot:
    if not source_transaction_id.strip():
        raise ValueError("purchased lots require a verified transaction id")
    return grant_lot(
        tenant_id=tenant_id,
        lot_id=lot_id,
        kind="purchased",
        period_id=source_transaction_id,
        amount=amount,
        expires=False,
        catalog_version=source_transaction_id,
    )


def can_start_generative(tenant_id: str) -> bool:
    from services.membership.period_grants import ensure_included_grant

    ensure_included_grant(tenant_id)
    return remaining_messages(tenant_id) >= 1


def expire_included_before(tenant_id: str, period_id: str) -> int:
    tid = tenant_id.strip()
    cleared = 0
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_expire_included_before

            cleared += pg_expire_included_before(session, tenant_id=tid, period_id=period_id)
    with _LOCK:
        for lot in _LOTS.get(tid, []):
            if lot.kind != "included" or not lot.expires or lot.period_id == period_id:
                continue
            if lot.remaining:
                lot.remaining = 0
                cleared += 1
    return cleared


def _pick_lot(lots: list[MessageLot]) -> MessageLot | None:
    included = [lot for lot in lots if lot.kind == "included" and _live_remaining(lot) > 0]
    if included:
        return included[0]
    purchased = [lot for lot in lots if lot.kind != "included" and _live_remaining(lot) > 0]
    return purchased[0] if purchased else None


def reserve(
    *,
    tenant_id: str,
    operation_id: str,
    response_class: ResponseClass,
) -> MessageReservation:
    units = message_units_for(response_class)
    tid = tenant_id.strip()
    key = _res_key(tid, operation_id)
    created = _now()
    from services.membership.period_grants import ensure_included_grant

    ensure_included_grant(tid)
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_reserve

            try:
                return pg_reserve(session, tenant_id=tid, operation_id=operation_id, response_class=response_class)
            except InsufficientMessages:
                pass
    with _LOCK:
        existing = _RESERVATIONS.get(key)
        if existing is not None:
            if existing.response_class and existing.response_class != response_class:
                raise ReservationConflict(f"operation {operation_id} already classified")
            return existing
        if units == 0:
            reservation = MessageReservation(
                reservation_id=key,
                tenant_id=tid,
                operation_id=operation_id,
                units=0,
                status="not_required",
                response_class=response_class,
                created_at=created,
            )
            _RESERVATIONS[key] = reservation
            return reservation
        held = sum(
            item.units
            for item in _RESERVATIONS.values()
            if item.tenant_id == tid and item.status == "reserved"
        )
        available = sum(_live_remaining(lot) for lot in _LOTS.get(tid, [])) - held
        if available < units:
            raise InsufficientMessages(tid, max(0, available))
        lot = _pick_lot(_LOTS.get(tid, []))
        reservation = MessageReservation(
            reservation_id=key,
            tenant_id=tid,
            operation_id=operation_id,
            units=units,
            status="reserved",
            lot_id=lot.lot_id if lot else "",
            period_id=lot.period_id if lot else "",
            response_class=response_class,
            created_at=created,
        )
        _RESERVATIONS[key] = reservation
        return reservation


def settle(*, tenant_id: str, operation_id: str, accepted: bool) -> MessageReservation:
    tid = tenant_id.strip()
    key = _res_key(tid, operation_id)
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_settle

            try:
                return pg_settle(session, tenant_id=tid, operation_id=operation_id, accepted=accepted)
            except KeyError:
                pass
    with _LOCK:
        reservation = _RESERVATIONS.get(key)
        if reservation is None:
            raise KeyError(operation_id)
        if reservation.status in {"settled", "released", "reversed", "not_required"}:
            return reservation
        if not accepted:
            reservation.status = "released"
            return reservation
        if reservation.units:
            lot = next((item for item in _LOTS.get(tid, []) if item.lot_id == reservation.lot_id), None)
            if lot is None or _live_remaining(lot) < reservation.units:
                lot = _pick_lot(_LOTS.get(tid, []))
            if lot is None or _live_remaining(lot) < reservation.units:
                raise InsufficientMessages(tid, lot.remaining if lot else 0)
            lot.remaining -= reservation.units
        reservation.status = "settled"
        return reservation


def reverse(*, tenant_id: str, operation_id: str) -> MessageReservation:
    tid = tenant_id.strip()
    key = _res_key(tid, operation_id)
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_reverse

            try:
                return pg_reverse(session, tenant_id=tid, operation_id=operation_id)
            except KeyError:
                pass
    with _LOCK:
        reservation = _RESERVATIONS.get(key)
        if reservation is None:
            raise KeyError(operation_id)
        if reservation.status == "reversed":
            return reservation
        if reservation.status == "settled" and reservation.units:
            lot = next((item for item in _LOTS.get(tid, []) if item.lot_id == reservation.lot_id), None)
            if lot is not None:
                lot.remaining += reservation.units
        reservation.status = "reversed"
        return reservation


def _lot_matches_txn(lot: MessageLot, transaction_id: str) -> bool:
    txn = transaction_id.strip()
    if not txn or lot.kind != "purchased":
        return False
    return lot.period_id == txn or lot.catalog_version == txn or lot.lot_id.endswith(f":{txn}")


def revoke_purchased(*, tenant_id: str, transaction_id: str) -> dict[str, Any]:
    """Zero unused purchased remaining for a verified refund. Keep lot history."""
    tid = tenant_id.strip()
    txn = transaction_id.strip()
    empty = {"revoked": False, "lot_ids": [], "remaining_cleared": 0, "reservations_released": 0}
    if not tid or not txn:
        return empty
    sql: dict[str, Any] = dict(empty)
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_revoke_purchased

            sql = pg_revoke_purchased(session, tenant_id=tid, transaction_id=txn)
    sql_ids = {str(item) for item in (sql.get("lot_ids") or [])}
    cleared = 0
    lot_ids: list[str] = []
    released = 0
    with _LOCK:
        for lot in _LOTS.get(tid, []):
            if lot.lot_id in sql_ids or not _lot_matches_txn(lot, txn):
                continue
            lot_ids.append(lot.lot_id)
            if lot.remaining:
                cleared += lot.remaining
                lot.remaining = 0
        known_lots = sql_ids | set(lot_ids)
        for reservation in _RESERVATIONS.values():
            if reservation.tenant_id != tid or reservation.status != "reserved":
                continue
            if reservation.lot_id in known_lots:
                reservation.status = "released"
                released += 1
    return {
        "revoked": bool(sql_ids or lot_ids),
        "lot_ids": list(sql.get("lot_ids") or []) + lot_ids,
        "remaining_cleared": int(sql.get("remaining_cleared") or 0) + cleared,
        "reservations_released": int(sql.get("reservations_released") or 0) + released,
    }


def list_stale_reserved(
    *,
    older_than: datetime,
    limit: int = 50,
    after_id: str = "",
) -> list[MessageReservation]:
    cap = max(1, min(int(limit), 200))
    stamp = older_than.isoformat()
    items: list[MessageReservation] = []
    seen: set[str] = set()
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_list_stale_reserved

            items = pg_list_stale_reserved(session, older_than=older_than, limit=cap, after_id=after_id)
            seen = {item.reservation_id for item in items}
    with _LOCK:
        for item in _RESERVATIONS.values():
            if item.status != "reserved" or str(item.created_at or "") > stamp:
                continue
            if item.reservation_id in seen:
                continue
            items.append(item)
            seen.add(item.reservation_id)
    items.sort(key=lambda item: item.reservation_id)
    if after_id:
        items = [item for item in items if item.reservation_id > after_id]
    return items[:cap]


def list_reservations(tenant_id: str | None = None) -> list[MessageReservation]:
    tid = (tenant_id or "").strip()
    items: list[MessageReservation] = []
    seen: set[tuple[str, str]] = set()
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_list_reservations

            items = pg_list_reservations(session, tenant_id=tid or None)
            seen = {(item.tenant_id, item.operation_id) for item in items}
    with _LOCK:
        for item in _RESERVATIONS.values():
            if tid and item.tenant_id != tid:
                continue
            key = (item.tenant_id, item.operation_id)
            if key in seen:
                continue
            items.append(item)
            seen.add(key)
    return items


def known_ledger_tenant_ids() -> list[str]:
    ids: set[str] = set()
    with _pg_session() as session:
        if session is not None:
            from services.membership.message_ledger_pg import pg_known_tenant_ids

            ids.update(pg_known_tenant_ids(session))
    with _LOCK:
        ids.update(_LOTS)
        ids.update(item.tenant_id for item in _RESERVATIONS.values())
    return sorted(tid for tid in ids if tid)


def snapshot_dict(tenant_id: str) -> dict[str, Any]:
    snap = snapshot(tenant_id)
    return {
        "tenant_id": snap.tenant_id,
        "included": snap.included,
        "purchased": snap.purchased,
        "reserved": snap.reserved,
        "remaining": snap.remaining,
        "lots": [
            {
                "lot_id": lot.lot_id,
                "kind": lot.kind,
                "period_id": lot.period_id,
                "granted": lot.granted,
                "remaining": lot.remaining,
                "expires": lot.expires,
                "live": lot_is_live(lot),
            }
            for lot in snap.lots
        ],
    }
