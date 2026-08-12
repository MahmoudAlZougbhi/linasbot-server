"""Postgres credit ledger (balances + append-only entries)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.credit_entitlements import CreditBalanceRow, CreditLedgerEntryRow


def get_balance_row(session: Session, tenant_id: str, *, for_update: bool = False) -> CreditBalanceRow | None:
    stmt = select(CreditBalanceRow).where(CreditBalanceRow.tenant_id == tenant_id)
    if for_update:
        stmt = stmt.with_for_update()
    return session.execute(stmt).scalar_one_or_none()


def read_balance(session: Session, tenant_id: str) -> tuple[int, int] | None:
    row = get_balance_row(session, tenant_id)
    if row is None:
        return None
    return int(row.available or 0), int(row.reserved or 0)


def upsert_balance(session: Session, tenant_id: str, available: int, reserved: int) -> CreditBalanceRow:
    row = get_balance_row(session, tenant_id, for_update=True)
    now = time.time()
    if row is None:
        row = CreditBalanceRow(
            tenant_id=tenant_id,
            available=int(available),
            reserved=int(reserved),
            updated_at=now,
        )
        session.add(row)
    else:
        row.available = int(available)
        row.reserved = int(reserved)
        row.updated_at = now
    session.flush()
    return row


def append_entry(session: Session, entry: dict[str, Any]) -> CreditLedgerEntryRow:
    row = CreditLedgerEntryRow(
        id=str(entry.get("id") or uuid.uuid4().hex),
        tenant_id=str(entry["tenant_id"]),
        user_id=entry.get("user_id"),
        op=str(entry["op"]),
        credits=int(entry.get("credits") or 0),
        balance_after=int(entry.get("balance_after") or 0),
        operation_type=str(entry.get("operation_type") or ""),
        model_provider=entry.get("model_provider"),
        provider_cost_usd=entry.get("provider_cost_usd"),
        request_id=entry.get("request_id"),
        created_at=float(entry.get("created_at") or time.time()),
        meta=dict(entry.get("meta") or {}),
    )
    session.add(row)
    session.flush()
    return row


def find_ops_by_request_id(session: Session, tenant_id: str, request_id: str) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(CreditLedgerEntryRow).where(
            CreditLedgerEntryRow.tenant_id == tenant_id,
            CreditLedgerEntryRow.request_id == request_id,
        )
    ).all()
    return [_entry_dict(r) for r in rows]


def reservation_state(session: Session, tenant_id: str, reservation_id: str) -> tuple[int, str | None]:
    credits = 0
    terminal: str | None = None
    rows = session.scalars(
        select(CreditLedgerEntryRow).where(CreditLedgerEntryRow.tenant_id == tenant_id)
    ).all()
    for row in rows:
        if row.id == reservation_id and row.op == "reserve":
            credits = int(row.credits)
        if row.request_id == reservation_id and row.op in {"capture", "release"}:
            terminal = str(row.op)
    return credits, terminal


def _entry_dict(row: CreditLedgerEntryRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "tenant_id": row.tenant_id,
        "user_id": row.user_id,
        "op": row.op,
        "credits": int(row.credits),
        "balance_after": int(row.balance_after),
        "operation_type": row.operation_type,
        "model_provider": row.model_provider,
        "provider_cost_usd": row.provider_cost_usd,
        "request_id": row.request_id,
        "created_at": float(row.created_at),
        "meta": dict(row.meta or {}),
    }


def import_balance(session: Session, tenant_id: str, available: int, reserved: int, updated_at: float) -> None:
    row = session.get(CreditBalanceRow, tenant_id)
    if row is None:
        session.add(
            CreditBalanceRow(
                tenant_id=tenant_id,
                available=int(available),
                reserved=int(reserved),
                updated_at=float(updated_at or time.time()),
            )
        )
    else:
        row.available = int(available)
        row.reserved = int(reserved)
        row.updated_at = float(updated_at or time.time())
    session.flush()


def import_entry(session: Session, entry: dict[str, Any]) -> bool:
    entry_id = str(entry.get("id") or "").strip()
    if not entry_id:
        entry_id = uuid.uuid4().hex
        entry = {**entry, "id": entry_id}
    if session.get(CreditLedgerEntryRow, entry_id) is not None:
        return False
    try:
        with session.begin_nested():
            append_entry(session, entry)
        return True
    except IntegrityError:
        return False
