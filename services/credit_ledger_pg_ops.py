"""Postgres-backed credit ledger operations (reserve/capture/grant/reverse)."""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError

from services.billing_backend import require_billing_pg_session
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
    with require_billing_pg_session() as session:
        bal = read_balance(session, tenant_id)
    if bal is not None:
        return int(bal[0])
    ent = entitlements_store.get(tenant_id)
    return int(ent.included_credits + ent.extra_credits)


def pg_get_reserved(tenant_id: str) -> int:
    with require_billing_pg_session() as session:
        bal = read_balance(session, tenant_id)
    return int(bal[1]) if bal is not None else 0


def ensure_period_grant_on_session(session: Any, tenant_id: str, *, plan_id: str, total: int) -> None:
    if get_balance_row(session, tenant_id, for_update=True) is not None:
        return
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
            "meta": {"plan_id": plan_id},
        },
    )


def pg_ensure_period_grant(tenant_id: str) -> None:
    ent = entitlements_store.get(tenant_id)
    with require_billing_pg_session() as session:
        ensure_period_grant_on_session(
            session,
            tenant_id,
            plan_id=ent.plan_id,
            total=int(ent.included_credits + ent.extra_credits),
        )


def grant_pack_on_session(
    session: Any,
    *,
    tenant_id: str,
    credits: int,
    request_id: str,
    source: str,
    meta: dict[str, Any] | None,
    bump_entitlement: bool = True,
) -> dict[str, Any]:
    """Idempotent grant_pack inside an existing session (for Apple atomic grants)."""
    from services.entitlements_pg_store import get_entitlement, save_entitlement

    ent_data = get_entitlement(session, tenant_id)
    if ent_data is None:
        ent = entitlements_store.get(tenant_id)
        plan_id = ent.plan_id
        included = int(ent.included_credits)
        extra = int(ent.extra_credits)
        total = included + extra
    else:
        plan_id = str(ent_data.get("plan_id") or "none")
        included = int(ent_data.get("included_credits") or 0)
        extra = int(ent_data.get("extra_credits") or 0)
        total = included + extra
    ensure_period_grant_on_session(session, tenant_id, plan_id=plan_id, total=total)
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
    if bump_entitlement:
        if ent_data is None:
            ent_data = {
                "tenant_id": tenant_id,
                "plan_id": plan_id,
                "status": "none",
                "source": "none",
                "current_period_end": None,
                "included_credits": included,
                "extra_credits": extra,
                "features": {},
                "updated_at": time.time(),
                "store_original_transaction_id": None,
            }
        ent_data = dict(ent_data)
        ent_data["extra_credits"] = int(ent_data.get("extra_credits") or 0) + int(credits)
        ent_data["updated_at"] = time.time()
        save_entitlement(session, ent_data)
    return {
        "duplicate": False,
        "op": "grant_pack",
        "credits": int(credits),
        "request_id": request_id,
        "ledger_entry_id": entry_id,
        "balance_after": available,
    }


def reverse_pack_on_session(
    session: Any,
    *,
    tenant_id: str,
    request_id: str,
    credits: int,
    meta: dict[str, Any] | None,
    bump_entitlement: bool = True,
) -> dict[str, Any]:
    from services.entitlements_pg_store import get_entitlement, save_entitlement

    ent_data = get_entitlement(session, tenant_id)
    if ent_data is None:
        ent = entitlements_store.get(tenant_id)
        plan_id = ent.plan_id
        total = int(ent.included_credits + ent.extra_credits)
    else:
        plan_id = str(ent_data.get("plan_id") or "none")
        total = int(ent_data.get("included_credits") or 0) + int(ent_data.get("extra_credits") or 0)
    ensure_period_grant_on_session(session, tenant_id, plan_id=plan_id, total=total)
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
    if bump_entitlement and ent_data is not None:
        ent_data = dict(ent_data)
        ent_data["extra_credits"] = max(0, int(ent_data.get("extra_credits") or 0) - int(credits))
        ent_data["updated_at"] = time.time()
        save_entitlement(session, ent_data)
    elif bump_entitlement:
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


def _open_reservation_from_prior(
    session: Any,
    tenant_id: str,
    prior: list[dict[str, Any]],
) -> str | None:
    for prior_row in prior:
        if prior_row.get("op") != "reserve":
            continue
        reservation_id = str(prior_row.get("id") or "").strip()
        if not reservation_id:
            continue
        row_credits, terminal = reservation_state(session, tenant_id, reservation_id)
        if row_credits > 0 and terminal is None:
            return reservation_id
    return None


def pg_find_open_reservation_by_request(tenant_id: str, request_id: str) -> str | None:
    """Return an open reservation id for ``request_id`` when reserve already committed."""
    rid = str(request_id or "").strip()
    if not rid:
        return None
    with require_billing_pg_session() as session:
        prior = find_ops_by_request_id(session, tenant_id, rid)
        return _open_reservation_from_prior(session, tenant_id, prior)


def pg_reserve(
    *,
    tenant_id: str,
    user_id: str | None,
    credits: int,
    operation_type: str,
    request_id: str,
) -> str:
    pg_ensure_period_grant(tenant_id)
    rid = str(request_id or "").strip()
    with require_billing_pg_session() as session:
        prior = find_ops_by_request_id(session, tenant_id, rid)
        existing = _open_reservation_from_prior(session, tenant_id, prior)
        if existing:
            return existing
        balance_row = get_balance_row(session, tenant_id, for_update=True)
        assert balance_row is not None
        available = int(balance_row.available)
        reserved = int(balance_row.reserved)
        if available < credits:
            raise PermissionError("Insufficient credits")
        reservation_id = uuid.uuid4().hex
        try:
            with session.begin_nested():
                available -= credits
                reserved += credits
                upsert_balance(session, tenant_id, available, reserved)
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
                        "request_id": rid,
                        "meta": {"reservation_id": reservation_id},
                    },
                )
        except IntegrityError:
            session.expire_all()
            raced = find_ops_by_request_id(session, tenant_id, rid)
            existing = _open_reservation_from_prior(session, tenant_id, raced)
            if existing:
                return existing
            raise
        return reservation_id


def pg_capture(
    *,
    tenant_id: str,
    reservation_id: str,
    provider_cost_usd: float | None,
    model_provider: str | None,
) -> dict[str, Any]:
    with require_billing_pg_session() as session:
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
    with require_billing_pg_session() as session:
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
    with require_billing_pg_session() as session:
        return grant_pack_on_session(
            session,
            tenant_id=tenant_id,
            credits=credits,
            request_id=request_id,
            source=source,
            meta=meta,
            bump_entitlement=True,
        )


def pg_reverse_pack(
    *,
    tenant_id: str,
    request_id: str,
    credits: int,
    meta: dict[str, Any] | None,
) -> dict[str, Any]:
    with require_billing_pg_session() as session:
        return reverse_pack_on_session(
            session,
            tenant_id=tenant_id,
            request_id=request_id,
            credits=credits,
            meta=meta,
            bump_entitlement=True,
        )
