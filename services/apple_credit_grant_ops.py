"""Apple consumable credit grant/reverse with durable idempotency.

When LINAS_BILLING_BACKEND=postgres: one Postgres transaction claims
AppleCreditGrantRow (PK) and applies the ledger + entitlement bump together.
IntegrityError on the grant PK makes concurrent retries idempotent.

When billing backend is file: claim AppleCreditGrantRow first (pending→granted
saga), then apply the file ledger so N retries still yield one credit effect.
"""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy.exc import IntegrityError

from db.models.apple_billing import AppleCreditGrantRow
from db.session import whatsapp_session
from services.billing_backend import billing_uses_postgres
from services.credit_ledger_service import credit_ledger_service
from services.iap_product_catalog import map_credit_product


def _duplicate_granted(row: AppleCreditGrantRow, *, transaction_id: str) -> dict[str, Any]:
    return {
        "kind": "credits",
        "duplicate": True,
        "credits": row.credits,
        "transaction_id": transaction_id,
    }


def _duplicate_reversed(row: AppleCreditGrantRow, *, transaction_id: str) -> dict[str, Any]:
    return {
        "kind": "credits",
        "duplicate": True,
        "reversed": True,
        "credits": row.credits,
        "transaction_id": transaction_id,
    }


def _result(
    *,
    grant_credits: int,
    transaction_id: str,
    ledger: dict[str, Any],
    allow_regrant_after_reverse: bool,
) -> dict[str, Any]:
    return {
        "kind": "credits",
        "duplicate": bool(ledger.get("duplicate")),
        "credits": grant_credits,
        "transaction_id": transaction_id,
        "ledger": ledger,
        "restored_after_refund_reversed": bool(allow_regrant_after_reverse),
    }


def _claim_pending_row(
    session: Any,
    *,
    transaction_id: str,
    tenant_id: str,
    product_id: str,
    grant_credits: int,
    allow_regrant_after_reverse: bool,
) -> AppleCreditGrantRow | dict[str, Any]:
    """Insert or reclaim grant row. Returns row to complete, or a duplicate result dict."""
    existing = session.get(AppleCreditGrantRow, transaction_id)
    if existing is not None and existing.status == "granted":
        return _duplicate_granted(existing, transaction_id=transaction_id)
    if existing is not None and existing.status == "reversed" and not allow_regrant_after_reverse:
        return _duplicate_reversed(existing, transaction_id=transaction_id)

    now = time.time()
    if existing is None:
        try:
            with session.begin_nested():
                row = AppleCreditGrantRow(
                    transaction_id=transaction_id,
                    tenant_id=tenant_id,
                    product_id=product_id,
                    credits=grant_credits,
                    status="pending",
                    granted_at=0.0,
                    reversed_at=None,
                    ledger_entry_id=None,
                    meta={"source": "apple"},
                )
                session.add(row)
                session.flush()
            return row
        except IntegrityError:
            existing = session.get(AppleCreditGrantRow, transaction_id)
            if existing is None:
                raise
            if existing.status == "granted":
                return _duplicate_granted(existing, transaction_id=transaction_id)
            if existing.status == "reversed" and not allow_regrant_after_reverse:
                return _duplicate_reversed(existing, transaction_id=transaction_id)
            return existing

    if existing.status == "reversed" and allow_regrant_after_reverse:
        existing.status = "pending"
        existing.reversed_at = None
        existing.credits = grant_credits
        meta = dict(existing.meta or {})
        meta["refund_reversed_restore"] = True
        existing.meta = meta
        existing.granted_at = 0.0
        session.flush()
        return existing

    # pending (or unexpected) — complete the saga
    if existing.status != "pending":
        existing.status = "pending"
        existing.granted_at = 0.0
        session.flush()
    _ = now
    return existing


def _mark_granted(
    row: AppleCreditGrantRow,
    *,
    grant_credits: int,
    ledger: dict[str, Any],
    ledger_request_id: str,
    allow_regrant_after_reverse: bool,
) -> None:
    now = time.time()
    row.status = "granted"
    row.granted_at = now
    row.reversed_at = None
    row.credits = grant_credits
    row.ledger_entry_id = str(ledger.get("ledger_entry_id") or row.ledger_entry_id or "") or None
    meta = dict(row.meta or {})
    if allow_regrant_after_reverse:
        meta["refund_reversed_restore"] = True
        meta["restore_ledger_request_id"] = ledger_request_id
    row.meta = meta


def grant_consumable_credits(
    *,
    tenant_id: str,
    product_id: str,
    transaction_id: str,
    allow_regrant_after_reverse: bool = False,
) -> dict[str, Any]:
    credits = map_credit_product(product_id)
    ledger_request_id = f"{transaction_id}:refund_reversed_restore" if allow_regrant_after_reverse else transaction_id

    if billing_uses_postgres():
        from services.credit_ledger_pg_ops import grant_pack_on_session

        with whatsapp_session(require=True) as session:
            prior = session.get(AppleCreditGrantRow, transaction_id)
            prior_credits = int(prior.credits) if prior is not None else credits
            grant_credits = prior_credits if allow_regrant_after_reverse else credits
            claimed = _claim_pending_row(
                session,
                transaction_id=transaction_id,
                tenant_id=tenant_id,
                product_id=product_id,
                grant_credits=grant_credits,
                allow_regrant_after_reverse=allow_regrant_after_reverse,
            )
            if isinstance(claimed, dict):
                return claimed
            ledger = grant_pack_on_session(
                session,
                tenant_id=tenant_id,
                credits=grant_credits,
                request_id=ledger_request_id,
                source="apple",
                meta={"product_id": product_id, "transaction_id": transaction_id},
                bump_entitlement=True,
            )
            _mark_granted(
                claimed,
                grant_credits=grant_credits,
                ledger=ledger,
                ledger_request_id=ledger_request_id,
                allow_regrant_after_reverse=allow_regrant_after_reverse,
            )
            return _result(
                grant_credits=grant_credits,
                transaction_id=transaction_id,
                ledger=ledger,
                allow_regrant_after_reverse=allow_regrant_after_reverse,
            )

    # File ledger saga: claim PG grant row first, then file ledger, then mark granted.
    with whatsapp_session(require=True) as session:
        prior = session.get(AppleCreditGrantRow, transaction_id)
        prior_credits = int(prior.credits) if prior is not None else credits
        grant_credits = prior_credits if allow_regrant_after_reverse else credits
        claimed = _claim_pending_row(
            session,
            transaction_id=transaction_id,
            tenant_id=tenant_id,
            product_id=product_id,
            grant_credits=grant_credits,
            allow_regrant_after_reverse=allow_regrant_after_reverse,
        )
        if isinstance(claimed, dict):
            return claimed

    ledger = credit_ledger_service.grant_pack(
        tenant_id=tenant_id,
        credits=grant_credits,
        request_id=ledger_request_id,
        source="apple",
        meta={"product_id": product_id, "transaction_id": transaction_id},
    )
    with whatsapp_session(require=True) as session:
        row = session.get(AppleCreditGrantRow, transaction_id)
        if row is None:
            raise RuntimeError("Apple credit grant claim missing after ledger write")
        if row.status == "granted":
            return _duplicate_granted(row, transaction_id=transaction_id)
        _mark_granted(
            row,
            grant_credits=grant_credits,
            ledger=ledger,
            ledger_request_id=ledger_request_id,
            allow_regrant_after_reverse=allow_regrant_after_reverse,
        )
    return _result(
        grant_credits=grant_credits,
        transaction_id=transaction_id,
        ledger=ledger,
        allow_regrant_after_reverse=allow_regrant_after_reverse,
    )


def reverse_consumable_credits(
    *,
    tenant_id: str,
    transaction_id: str,
    product_id: str | None = None,
) -> dict[str, Any]:
    with whatsapp_session(require=True) as session:
        row = session.get(AppleCreditGrantRow, transaction_id)
        if row is None:
            return {
                "kind": "credits_reverse",
                "skipped": True,
                "reason": "no_grant",
                "transaction_id": transaction_id,
            }
        if row.status == "reversed":
            return {
                "kind": "credits_reverse",
                "duplicate": True,
                "credits": row.credits,
                "transaction_id": transaction_id,
            }
        if row.status == "pending":
            # Never granted — mark reversed without inventing a debit.
            row.status = "reversed"
            row.reversed_at = time.time()
            return {
                "kind": "credits_reverse",
                "skipped": True,
                "reason": "pending_never_granted",
                "transaction_id": transaction_id,
                "credits": int(row.credits),
            }
        credits = int(row.credits)
        grant_tenant = row.tenant_id
        pid = product_id or row.product_id

    if grant_tenant != tenant_id:
        raise PermissionError("cross-tenant credit reverse denied")

    if billing_uses_postgres():
        from services.credit_ledger_pg_ops import reverse_pack_on_session

        with whatsapp_session(require=True) as session:
            row = session.get(AppleCreditGrantRow, transaction_id)
            if row is None:
                return {
                    "kind": "credits_reverse",
                    "skipped": True,
                    "reason": "no_grant",
                    "transaction_id": transaction_id,
                }
            if row.status == "reversed":
                return {
                    "kind": "credits_reverse",
                    "duplicate": True,
                    "credits": row.credits,
                    "transaction_id": transaction_id,
                }
            ledger = reverse_pack_on_session(
                session,
                tenant_id=tenant_id,
                request_id=transaction_id,
                credits=credits,
                meta={"product_id": pid, "source": "apple_refund"},
                bump_entitlement=True,
            )
            now = time.time()
            row.status = "reversed"
            row.reversed_at = now
            meta = dict(row.meta or {})
            if int(ledger.get("debt") or 0) > 0:
                meta["debt"] = int(ledger["debt"])
            meta["reverse_ledger_entry_id"] = ledger.get("ledger_entry_id")
            row.meta = meta
        return {
            "kind": "credits_reverse",
            "duplicate": bool(ledger.get("duplicate")),
            "credits": credits,
            "transaction_id": transaction_id,
            "debt": int(ledger.get("debt") or 0),
            "ledger": ledger,
        }

    ledger = credit_ledger_service.reverse_pack(
        tenant_id=tenant_id,
        request_id=transaction_id,
        credits=credits,
        meta={"product_id": pid, "source": "apple_refund"},
    )
    now = time.time()
    with whatsapp_session(require=True) as session:
        row = session.get(AppleCreditGrantRow, transaction_id)
        if row is not None:
            row.status = "reversed"
            row.reversed_at = now
            meta = dict(row.meta or {})
            if int(ledger.get("debt") or 0) > 0:
                meta["debt"] = int(ledger["debt"])
            meta["reverse_ledger_entry_id"] = ledger.get("ledger_entry_id")
            row.meta = meta
    return {
        "kind": "credits_reverse",
        "duplicate": bool(ledger.get("duplicate")),
        "credits": credits,
        "transaction_id": transaction_id,
        "debt": int(ledger.get("debt") or 0),
        "ledger": ledger,
    }
