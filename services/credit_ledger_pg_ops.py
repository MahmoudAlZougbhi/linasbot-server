"""Postgres-backed credit ledger operations (reserve/capture/grant/reverse)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from db.session import whatsapp_session
from services.credit_ledger_pg_store import (
    append_entry,
    find_ops_by_request_id,
    get_balance_row,
    read_balance,
    reservation_state,
    upsert_balance,
)
from services.entitlements_service import entitlements_store


def pg_get_balance(tenant_id: str) -> int:
    with whatsapp_session() as session:
        bal = read_balance(session, tenant_id)
    if bal is not None:
        return int(bal[0])
    ent = entitlements_store.get(tenant_id)
    return int(ent.included_credits + ent.extra_credits)


def pg_get_reserved(tenant_id: str) -> int:
    with whatsapp_session() as session:
        bal = read_balance(session, tenant_id)
    return int(bal[1]) if bal is not None else 0


def pg_ensure_period_grant(tenant_id: str) -> None:
    ent = entitlements_store.get(tenant_id)
    with whatsapp_session() as session:
        if get_balance_row(session, tenant_id, for_update=True) is not None:
            return
        total = int(ent.included_credits + ent.extra_credits)
        upsert_balance(session, tenant_id, total, 0)
        append_entry(
            session,
            {
                "id": uuid.uuid4().hex,
                "tenant_id": tenant_id,
                "op": "grant_included",
                "credits": total,
                "balance_after": total,
                "operation_type": "period_grant",
                "created_at": time.time(),
                "meta": {"plan_id": ent.plan_id},
            },
        )


def pg_reserve(
    *,
    tenant_id: str,
    user_id: str | None,
    credits: int,
    operation_type: str,
    request_id: str,
) -> str:
    pg_ensure_period_grant(tenant_id)
    with whatsapp_session() as session:
        row = get_balance_row(session, tenant_id, for_update=True)
        assert row is not None
        available = int(row.available)
        reserved = int(row.reserved)
        if available < credits:
            raise PermissionError("Insufficient credits")
        available -= credits
        reserved += credits
        upsert_balance(session, tenant_id, available, reserved)
        reservation_id = uuid.uuid4().hex
        append_entry(
            session,
            {
                "id": reservation_id,
                "tenant_id": tenant_id,
                "user_id": user_id,
                "op": "reserve",
                "credits": credits,
                "balance_after": available,
                "operation_type": operation_type,
                "request_id": request_id,
                "meta": {"reservation_id": reservation_id},
            },
        )
        return reservation_id


def pg_capture(
    *,
    tenant_id: str,
    reservation_id: str,
    provider_cost_usd: float | None,
    model_provider: str | None,
) -> dict[str, Any]:
    with whatsapp_session() as session:
        get_balance_row(session, tenant_id, for_update=True)
        credits, terminal = reservation_state(session, tenant_id, reservation_id)
        if credits <= 0:
            raise ValueError("Unknown reservation")
        if terminal == "capture":
            return {"duplicate": True, "op": "capture"}
        if terminal == "release":
            raise PermissionError("Reservation already released")
        row = get_balance_row(session, tenant_id)
        assert row is not None
        reserved = max(0, int(row.reserved) - credits)
        available = int(row.available)
        upsert_balance(session, tenant_id, available, reserved)
        append_entry(
            session,
            {
                "id": uuid.uuid4().hex,
                "tenant_id": tenant_id,
                "op": "capture",
                "credits": credits,
                "balance_after": available,
                "operation_type": "capture",
                "model_provider": model_provider,
                "provider_cost_usd": provider_cost_usd,
                "request_id": reservation_id,
            },
        )
        return {"duplicate": False, "op": "capture", "credits": credits}


def pg_release(*, tenant_id: str, reservation_id: str) -> dict[str, Any]:
    with whatsapp_session() as session:
        get_balance_row(session, tenant_id, for_update=True)
        credits, terminal = reservation_state(session, tenant_id, reservation_id)
        if credits <= 0:
            return {"duplicate": False, "op": "release", "skipped": True}
        if terminal == "release":
            return {"duplicate": True, "op": "release"}
        if terminal == "capture":
            return {"duplicate": True, "op": "capture", "skipped": True}
        row = get_balance_row(session, tenant_id)
        assert row is not None
        available = int(row.available) + credits
        reserved = max(0, int(row.reserved) - credits)
        upsert_balance(session, tenant_id, available, reserved)
        append_entry(
            session,
            {
                "id": uuid.uuid4().hex,
                "tenant_id": tenant_id,
                "op": "release",
                "credits": credits,
                "balance_after": available,
                "operation_type": "release",
                "request_id": reservation_id,
            },
        )
        return {"duplicate": False, "op": "release", "credits": credits}


def pg_grant_pack(
    *,
    tenant_id: str,
    credits: int,
    request_id: str,
    source: str,
    meta: dict[str, Any] | None,
) -> dict[str, Any]:
    pg_ensure_period_grant(tenant_id)
    with whatsapp_session() as session:
        get_balance_row(session, tenant_id, for_update=True)
        prior = find_ops_by_request_id(session, tenant_id, request_id)
        if any(r.get("op") == "grant_pack" for r in prior):
            return {
                "duplicate": True,
                "op": "grant_pack",
                "credits": credits,
                "request_id": request_id,
            }
        row = get_balance_row(session, tenant_id)
        assert row is not None
        available = int(row.available) + int(credits)
        reserved = int(row.reserved)
        upsert_balance(session, tenant_id, available, reserved)
        entry_id = uuid.uuid4().hex
        append_entry(
            session,
            {
                "id": entry_id,
                "tenant_id": tenant_id,
                "op": "grant_pack",
                "credits": int(credits),
                "balance_after": available,
                "operation_type": "pack_grant",
                "request_id": request_id,
                "meta": {"source": source, **(meta or {})},
            },
        )
    ent = entitlements_store.get(tenant_id)
    ent.extra_credits = int(ent.extra_credits) + int(credits)
    entitlements_store.save(ent)
    return {
        "duplicate": False,
        "op": "grant_pack",
        "credits": int(credits),
        "request_id": request_id,
        "ledger_entry_id": entry_id,
        "balance_after": available,
    }


def pg_reverse_pack(
    *,
    tenant_id: str,
    request_id: str,
    credits: int,
    meta: dict[str, Any] | None,
) -> dict[str, Any]:
    pg_ensure_period_grant(tenant_id)
    with whatsapp_session() as session:
        get_balance_row(session, tenant_id, for_update=True)
        prior = find_ops_by_request_id(session, tenant_id, request_id)
        if any(r.get("op") == "reverse_pack" for r in prior):
            return {
                "duplicate": True,
                "op": "reverse_pack",
                "credits": credits,
                "request_id": request_id,
            }
        row = get_balance_row(session, tenant_id)
        assert row is not None
        available = int(row.available)
        reserved = int(row.reserved)
        reduce_by = min(available, int(credits))
        debt = int(credits) - reduce_by
        available = available - reduce_by
        upsert_balance(session, tenant_id, available, reserved)
        entry_id = uuid.uuid4().hex
        append_entry(
            session,
            {
                "id": entry_id,
                "tenant_id": tenant_id,
                "op": "reverse_pack",
                "credits": int(credits),
                "balance_after": available,
                "operation_type": "pack_reverse",
                "request_id": request_id,
                "meta": {"debt": debt, "reduced": reduce_by, **(meta or {})},
            },
        )
    ent = entitlements_store.get(tenant_id)
    ent.extra_credits = max(0, int(ent.extra_credits) - int(credits))
    entitlements_store.save(ent)
    return {
        "duplicate": False,
        "op": "reverse_pack",
        "credits": int(credits),
        "request_id": request_id,
        "ledger_entry_id": entry_id,
        "balance_after": available,
        "debt": debt,
        "reduced": reduce_by,
    }
