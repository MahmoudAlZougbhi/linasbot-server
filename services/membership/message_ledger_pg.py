"""Postgres implementations for the message entitlement ledger."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import text

from services.membership.lot_window import current_period_id, lot_is_live
from services.membership.message_ledger import (
    InsufficientMessages,
    LedgerSnapshot,
    MessageLot,
    MessageReservation,
    ReservationConflict,
)
from services.membership.message_policy import ResponseClass, message_units_for


def _now() -> str:
    return datetime.now(UTC).isoformat()


def pg_grant_lot(
    session: Any,
    *,
    tenant_id: str,
    lot_id: str,
    kind: str,
    period_id: str,
    amount: int,
    expires: bool,
    catalog_version: str,
) -> MessageLot:
    existing = (
        session.execute(
            text(
                "SELECT lot_id, tenant_id, kind, period_id, granted, remaining, expires, catalog_version "
                "FROM customer_ai_message_lots WHERE lot_id = :lot_id"
            ),
            {"lot_id": lot_id},
        )
        .mappings()
        .first()
    )
    if existing:
        return MessageLot(**dict(existing))
    session.execute(
        text(
            "INSERT INTO customer_ai_message_lots "
            "(lot_id, tenant_id, kind, period_id, granted, remaining, expires, catalog_version) "
            "VALUES (:lot_id, :tenant_id, :kind, :period_id, :granted, :remaining, :expires, :catalog_version)"
        ),
        {
            "lot_id": lot_id,
            "tenant_id": tenant_id,
            "kind": kind,
            "period_id": period_id,
            "granted": amount,
            "remaining": amount,
            "expires": expires,
            "catalog_version": catalog_version,
        },
    )
    return MessageLot(
        lot_id=lot_id,
        tenant_id=tenant_id,
        kind=kind,
        period_id=period_id,
        granted=amount,
        remaining=amount,
        expires=expires,
        catalog_version=catalog_version,
    )


def pg_snapshot(session: Any, tenant_id: str) -> LedgerSnapshot:
    lots_rows = (
        session.execute(
            text(
                "SELECT lot_id, tenant_id, kind, period_id, granted, remaining, expires, catalog_version "
                "FROM customer_ai_message_lots WHERE tenant_id = :tid"
            ),
            {"tid": tenant_id},
        )
        .mappings()
        .all()
    )
    lots = [MessageLot(**dict(row)) for row in lots_rows]
    reserved = session.execute(
        text(
            "SELECT COALESCE(SUM(units), 0) FROM customer_ai_message_reservations "
            "WHERE tenant_id = :tid AND status = 'reserved'"
        ),
        {"tid": tenant_id},
    ).scalar()
    reserved_i = int(reserved or 0)
    included = sum(lot.remaining for lot in lots if lot.kind == "included" and lot_is_live(lot))
    purchased = sum(lot.remaining for lot in lots if lot.kind == "purchased" and lot_is_live(lot))
    return LedgerSnapshot(
        tenant_id=tenant_id,
        included=included,
        purchased=purchased,
        reserved=reserved_i,
        remaining=max(0, included + purchased - reserved_i),
        lots=lots,
    )


def _row_lock(session: Any) -> str:
    bind = session.get_bind()
    return " FOR UPDATE" if getattr(bind.dialect, "name", "") != "sqlite" else ""


def _pick_lot(session: Any, tenant_id: str) -> MessageLot | None:
    row = (
        session.execute(
            text(
                "SELECT lot_id, tenant_id, kind, period_id, granted, remaining, expires, catalog_version "
                "FROM customer_ai_message_lots WHERE tenant_id = :tid AND remaining > 0 "
                "AND (expires = false OR period_id = :period) "
                "ORDER BY CASE WHEN kind = 'included' THEN 0 ELSE 1 END, created_at" + _row_lock(session)
            ),
            {"tid": tenant_id, "period": current_period_id()},
        )
        .mappings()
        .first()
    )
    return MessageLot(**dict(row)) if row else None


def pg_expire_included_before(session: Any, *, tenant_id: str, period_id: str) -> int:
    result = session.execute(
        text(
            "UPDATE customer_ai_message_lots SET remaining = 0 "
            "WHERE tenant_id = :tid AND kind = 'included' AND expires = true "
            "AND period_id <> :period AND remaining > 0"
        ),
        {"tid": tenant_id, "period": period_id},
    )
    return int(result.rowcount or 0)


def pg_reserve(
    session: Any,
    *,
    tenant_id: str,
    operation_id: str,
    response_class: ResponseClass,
) -> MessageReservation:
    units = message_units_for(response_class)
    key = f"{tenant_id}:{operation_id}"
    existing = (
        session.execute(
            text(
                "SELECT reservation_id, tenant_id, operation_id, units, status, lot_id, period_id, "
                "response_class, created_at FROM customer_ai_message_reservations "
                "WHERE reservation_id = :rid"
            ),
            {"rid": key},
        )
        .mappings()
        .first()
    )
    if existing:
        if existing["response_class"] and existing["response_class"] != response_class:
            raise ReservationConflict(f"operation {operation_id} already classified")
        return MessageReservation(**dict(existing))
    if units == 0:
        reservation = MessageReservation(
            reservation_id=key,
            tenant_id=tenant_id,
            operation_id=operation_id,
            units=0,
            status="not_required",
            response_class=response_class,
            created_at=_now(),
        )
        _insert_reservation(session, reservation)
        return reservation
    snap = pg_snapshot(session, tenant_id)
    if snap.remaining < units:
        raise InsufficientMessages(tenant_id, snap.remaining)
    lot = _pick_lot(session, tenant_id)
    reservation = MessageReservation(
        reservation_id=key,
        tenant_id=tenant_id,
        operation_id=operation_id,
        units=units,
        status="reserved",
        lot_id=lot.lot_id if lot else "",
        period_id=lot.period_id if lot else "",
        response_class=response_class,
        created_at=_now(),
    )
    _insert_reservation(session, reservation)
    return reservation


def _insert_reservation(session: Any, reservation: MessageReservation) -> None:
    session.execute(
        text(
            "INSERT INTO customer_ai_message_reservations "
            "(reservation_id, tenant_id, operation_id, units, status, lot_id, period_id, response_class, created_at) "
            "VALUES (:reservation_id, :tenant_id, :operation_id, :units, :status, :lot_id, :period_id, :response_class, :created_at)"
        ),
        reservation.__dict__,
    )


def pg_settle(session: Any, *, tenant_id: str, operation_id: str, accepted: bool) -> MessageReservation:
    key = f"{tenant_id}:{operation_id}"
    row = (
        session.execute(
            text(
                "SELECT reservation_id, tenant_id, operation_id, units, status, lot_id, period_id, "
                "response_class, created_at FROM customer_ai_message_reservations "
                "WHERE reservation_id = :rid" + _row_lock(session)
            ),
            {"rid": key},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise KeyError(operation_id)
    reservation = MessageReservation(**dict(row))
    if reservation.status in {"settled", "released", "reversed", "not_required"}:
        return reservation
    if not accepted:
        session.execute(
            text("UPDATE customer_ai_message_reservations SET status = 'released' WHERE reservation_id = :rid"),
            {"rid": key},
        )
        reservation.status = "released"
        return reservation
    if reservation.units:
        lot = session.execute(
            text("SELECT remaining FROM customer_ai_message_lots WHERE lot_id = :lot" + _row_lock(session)),
            {"lot": reservation.lot_id},
        ).first()
        remaining = int(lot[0]) if lot else 0
        target = reservation.lot_id
        if lot is None or remaining < reservation.units:
            fallback = _pick_lot(session, tenant_id)
            if fallback is None or fallback.remaining < reservation.units:
                raise InsufficientMessages(tenant_id, remaining)
            target = fallback.lot_id
            reservation.lot_id = target
        session.execute(
            text("UPDATE customer_ai_message_lots SET remaining = remaining - :u WHERE lot_id = :lot"),
            {"u": reservation.units, "lot": target},
        )
    session.execute(
        text("UPDATE customer_ai_message_reservations SET status = 'settled' WHERE reservation_id = :rid"),
        {"rid": key},
    )
    reservation.status = "settled"
    return reservation


def pg_list_stale_reserved(
    session: Any,
    *,
    older_than: datetime,
    limit: int = 50,
    after_id: str = "",
) -> list[MessageReservation]:
    rows = (
        session.execute(
            text(
                "SELECT reservation_id, tenant_id, operation_id, units, status, lot_id, period_id, "
                "response_class, created_at FROM customer_ai_message_reservations "
                "WHERE status = 'reserved' AND created_at < :cutoff "
                "AND reservation_id > :after ORDER BY reservation_id LIMIT :lim"
            ),
            {"cutoff": older_than, "after": after_id or "", "lim": max(1, min(int(limit), 200))},
        )
        .mappings()
        .all()
    )
    items: list[MessageReservation] = []
    for row in rows:
        data = dict(row)
        created = data.get("created_at")
        if hasattr(created, "isoformat"):
            data["created_at"] = created.isoformat()
        items.append(MessageReservation(**data))
    return items


def pg_list_reservations(session: Any, *, tenant_id: str | None = None) -> list[MessageReservation]:
    sql = (
        "SELECT reservation_id, tenant_id, operation_id, units, status, lot_id, period_id, "
        "response_class, created_at FROM customer_ai_message_reservations"
    )
    params: dict[str, Any] = {}
    if tenant_id:
        sql += " WHERE tenant_id = :tid"
        params["tid"] = tenant_id
    rows = session.execute(text(sql), params).mappings().all()
    items: list[MessageReservation] = []
    for row in rows:
        data = dict(row)
        created = data.get("created_at")
        if hasattr(created, "isoformat"):
            data["created_at"] = created.isoformat()
        items.append(MessageReservation(**data))
    return items


def pg_known_tenant_ids(session: Any) -> list[str]:
    lots = session.execute(text("SELECT DISTINCT tenant_id FROM customer_ai_message_lots")).scalars().all()
    reserved = session.execute(text("SELECT DISTINCT tenant_id FROM customer_ai_message_reservations")).scalars().all()
    return sorted({str(item) for item in [*lots, *reserved] if item})


def pg_reverse(session: Any, *, tenant_id: str, operation_id: str) -> MessageReservation:
    key = f"{tenant_id}:{operation_id}"
    row = (
        session.execute(
            text(
                "SELECT reservation_id, tenant_id, operation_id, units, status, lot_id, period_id, "
                "response_class, created_at FROM customer_ai_message_reservations "
                "WHERE reservation_id = :rid" + _row_lock(session)
            ),
            {"rid": key},
        )
        .mappings()
        .first()
    )
    if row is None:
        raise KeyError(operation_id)
    reservation = MessageReservation(**dict(row))
    if reservation.status == "reversed":
        return reservation
    if reservation.status == "settled" and reservation.units and reservation.lot_id:
        session.execute(
            text("UPDATE customer_ai_message_lots SET remaining = remaining + :u WHERE lot_id = :lot"),
            {"u": reservation.units, "lot": reservation.lot_id},
        )
    session.execute(
        text("UPDATE customer_ai_message_reservations SET status = 'reversed' WHERE reservation_id = :rid"),
        {"rid": key},
    )
    reservation.status = "reversed"
    return reservation


def pg_revoke_purchased(session: Any, *, tenant_id: str, transaction_id: str) -> dict[str, Any]:
    suffix = f"%:{transaction_id}"
    rows = (
        session.execute(
            text(
                "SELECT lot_id, remaining FROM customer_ai_message_lots "
                "WHERE tenant_id = :tid AND kind = 'purchased' "
                "AND (period_id = :txn OR catalog_version = :txn OR lot_id LIKE :suffix)" + _row_lock(session)
            ),
            {"tid": tenant_id, "txn": transaction_id, "suffix": suffix},
        )
        .mappings()
        .all()
    )
    lot_ids = [str(row["lot_id"]) for row in rows]
    cleared = 0
    for row in rows:
        remaining = int(row["remaining"] or 0)
        if remaining:
            session.execute(
                text("UPDATE customer_ai_message_lots SET remaining = 0 WHERE lot_id = :lot"),
                {"lot": row["lot_id"]},
            )
            cleared += remaining
    released = 0
    for lot_id in lot_ids:
        result = session.execute(
            text(
                "UPDATE customer_ai_message_reservations SET status = 'released' "
                "WHERE tenant_id = :tid AND status = 'reserved' AND lot_id = :lot"
            ),
            {"tid": tenant_id, "lot": lot_id},
        )
        released += int(result.rowcount or 0)
    return {
        "revoked": bool(lot_ids),
        "lot_ids": lot_ids,
        "remaining_cleared": cleared,
        "reservations_released": released,
    }
