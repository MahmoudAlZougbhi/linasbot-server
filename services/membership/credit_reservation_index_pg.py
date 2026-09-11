"""Optional SQL persistence for leftover-credit reservation index rows."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text

from services.membership.credit_reservation_index import OpenCreditReservation


def table_ready(session: Any) -> bool:
    try:
        bind = session.get_bind()
        if bind.dialect.name == "sqlite":
            row = session.execute(
                text(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='customer_ai_credit_reservation_index'"
                )
            ).first()
            return bool(row and row[0])
        row = session.execute(text("SELECT to_regclass('customer_ai_credit_reservation_index')")).first()
        return bool(row and row[0])
    except Exception:
        return False


def pg_reset(session: Any) -> None:
    session.execute(text("DELETE FROM customer_ai_credit_reservation_index"))


def pg_upsert(session: Any, item: OpenCreditReservation) -> None:
    session.execute(
        text(
            "INSERT INTO customer_ai_credit_reservation_index ("
            "reservation_id, tenant_id, request_id, operation_type, created_at, state"
            ") VALUES ("
            ":reservation_id, :tenant_id, :request_id, :operation_type, :created_at, :state"
            ") ON CONFLICT (reservation_id) DO UPDATE SET "
            "request_id=:request_id, operation_type=:operation_type, state=:state"
        ),
        {
            "reservation_id": item.reservation_id,
            "tenant_id": item.tenant_id,
            "request_id": item.request_id,
            "operation_type": item.operation_type,
            "created_at": item.created_at,
            "state": item.state,
        },
    )


def _row(raw: Any) -> OpenCreditReservation:
    return OpenCreditReservation(
        reservation_id=str(raw["reservation_id"]),
        tenant_id=str(raw.get("tenant_id") or ""),
        request_id=str(raw.get("request_id") or ""),
        operation_type=str(raw.get("operation_type") or ""),
        created_at=str(raw.get("created_at") or ""),
        state=str(raw.get("state") or "reserved"),
    )


def pg_get(session: Any, reservation_id: str) -> OpenCreditReservation | None:
    row = (
        session.execute(
            text(
                "SELECT reservation_id, tenant_id, request_id, operation_type, created_at, state "
                "FROM customer_ai_credit_reservation_index WHERE reservation_id = :rid"
            ),
            {"rid": reservation_id},
        )
        .mappings()
        .first()
    )
    return _row(dict(row)) if row else None


def pg_delete(session: Any, reservation_id: str) -> None:
    session.execute(
        text("DELETE FROM customer_ai_credit_reservation_index WHERE reservation_id = :rid"),
        {"rid": reservation_id},
    )


def pg_list(session: Any, *, tenant_id: str = "", state: str = "reserved") -> list[OpenCreditReservation]:
    sql = (
        "SELECT reservation_id, tenant_id, request_id, operation_type, created_at, state "
        "FROM customer_ai_credit_reservation_index WHERE state = :state"
    )
    params: dict[str, Any] = {"state": state}
    if tenant_id:
        sql += " AND tenant_id = :tid"
        params["tid"] = tenant_id
    sql += " ORDER BY reservation_id"
    rows = session.execute(text(sql), params).mappings().all()
    return [_row(dict(row)) for row in rows]


def pg_tenant_ids(session: Any) -> list[str]:
    rows = session.execute(text("SELECT DISTINCT tenant_id FROM customer_ai_credit_reservation_index")).all()
    return sorted(str(row[0]) for row in rows if row and row[0])


def pg_reservation_ids(session: Any, *, tenant_id: str = "") -> set[str]:
    sql = "SELECT reservation_id FROM customer_ai_credit_reservation_index"
    params: dict[str, Any] = {}
    if tenant_id:
        sql += " WHERE tenant_id = :tid"
        params["tid"] = tenant_id
    return {str(row[0]) for row in session.execute(text(sql), params).all() if row and row[0]}
