"""Apple IAP side-effects: subscription entitlements + consumable credit grants."""

from __future__ import annotations

import time
from typing import Any

from db.models.apple_billing import AppleAppAccountTokenRow, AppleCreditGrantRow
from db.session import whatsapp_session
from services.credit_ledger_service import credit_ledger_service
from services.entitlements_service import EntitlementStatus, apply_store_notification, entitlements_store
from services.iap_product_catalog import (
    is_credit_product,
    is_subscription_product,
    map_credit_product,
    map_subscription_product,
)
from services.store_iap_service import normalize_apple_status


def lookup_tenant_by_app_account_token(app_account_token: str) -> tuple[str, str] | None:
    token = str(app_account_token or "").strip().lower()
    if not token:
        return None
    with whatsapp_session() as session:
        row = session.get(AppleAppAccountTokenRow, token)
        if row is None:
            # Apple may send UUID mixed-case — try as-is primary already lowercased.
            row = session.get(AppleAppAccountTokenRow, str(app_account_token or "").strip())
        if row is None:
            return None
        return row.tenant_id, row.user_id


def get_or_create_app_account_token(*, tenant_id: str, user_id: str) -> str:
    import uuid

    tid = str(tenant_id or "").strip()
    uid = str(user_id or "").strip()
    if not tid or not uid:
        raise ValueError("tenant_id and user_id required")
    with whatsapp_session() as session:
        from sqlalchemy import select

        existing = session.scalars(
            select(AppleAppAccountTokenRow).where(
                AppleAppAccountTokenRow.tenant_id == tid,
                AppleAppAccountTokenRow.user_id == uid,
            )
        ).first()
        if existing is not None:
            return existing.app_account_token
        token = str(uuid.uuid4())
        session.add(
            AppleAppAccountTokenRow(
                app_account_token=token,
                tenant_id=tid,
                user_id=uid,
                created_at=time.time(),
            )
        )
        session.flush()
        return token


def subscription_status_from_payload(
    payload: dict[str, Any],
    *,
    notification_type: str | None = None,
) -> EntitlementStatus:
    if payload.get("revocationDate"):
        return "revoked"
    if notification_type:
        return normalize_apple_status(notification_type)
    expires_ms = payload.get("expiresDate")
    if expires_ms is not None:
        try:
            if int(expires_ms) <= int(time.time() * 1000):
                return "expired"
        except (TypeError, ValueError):
            pass
    return "active"


def apply_subscription_effect(
    *,
    tenant_id: str,
    product_id: str,
    original_transaction_id: str,
    status: EntitlementStatus,
    idempotency_key: str,
) -> dict[str, Any]:
    plan_id = map_subscription_product(product_id)
    result = apply_store_notification(
        tenant_id=tenant_id,
        plan_id=plan_id,  # type: ignore[arg-type]
        status=status,
        source="apple",
        original_transaction_id=original_transaction_id,
        idempotency_key=idempotency_key,
    )
    # Also stamp store_original_transaction_id via set_plan path already done.
    return {"kind": "subscription", "plan_id": plan_id, "status": status, **result}


def grant_consumable_credits(
    *,
    tenant_id: str,
    product_id: str,
    transaction_id: str,
) -> dict[str, Any]:
    credits = map_credit_product(product_id)
    with whatsapp_session() as session:
        existing = session.get(AppleCreditGrantRow, transaction_id)
        if existing is not None and existing.status == "granted":
            return {
                "kind": "credits",
                "duplicate": True,
                "credits": existing.credits,
                "transaction_id": transaction_id,
            }
        if existing is not None and existing.status == "reversed":
            return {
                "kind": "credits",
                "duplicate": True,
                "reversed": True,
                "credits": existing.credits,
                "transaction_id": transaction_id,
            }

    ledger = credit_ledger_service.grant_pack(
        tenant_id=tenant_id,
        credits=credits,
        request_id=transaction_id,
        source="apple",
        meta={"product_id": product_id},
    )
    now = time.time()
    with whatsapp_session() as session:
        row = session.get(AppleCreditGrantRow, transaction_id)
        if row is None:
            session.add(
                AppleCreditGrantRow(
                    transaction_id=transaction_id,
                    tenant_id=tenant_id,
                    product_id=product_id,
                    credits=credits,
                    status="granted",
                    granted_at=now,
                    reversed_at=None,
                    ledger_entry_id=str(ledger.get("ledger_entry_id") or "") or None,
                    meta={"source": "apple"},
                )
            )
        elif row.status != "granted":
            row.status = "granted"
            row.granted_at = now
            row.ledger_entry_id = str(ledger.get("ledger_entry_id") or row.ledger_entry_id)
    return {
        "kind": "credits",
        "duplicate": bool(ledger.get("duplicate")),
        "credits": credits,
        "transaction_id": transaction_id,
        "ledger": ledger,
    }


def reverse_consumable_credits(
    *,
    tenant_id: str,
    transaction_id: str,
    product_id: str | None = None,
) -> dict[str, Any]:
    with whatsapp_session() as session:
        row = session.get(AppleCreditGrantRow, transaction_id)
        if row is None:
            # No prior grant recorded — nothing to reverse (do not invent free credits).
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
        credits = int(row.credits)
        grant_tenant = row.tenant_id
        pid = product_id or row.product_id

    if grant_tenant != tenant_id:
        raise PermissionError("cross-tenant credit reverse denied")

    ledger = credit_ledger_service.reverse_pack(
        tenant_id=tenant_id,
        request_id=transaction_id,
        credits=credits,
        meta={"product_id": pid, "source": "apple_refund"},
    )
    now = time.time()
    with whatsapp_session() as session:
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


def classify_product(product_id: str) -> str:
    if is_subscription_product(product_id):
        return "subscription"
    if is_credit_product(product_id):
        return "consumable"
    raise ValueError(f"Unmapped Apple product: {product_id}")


def bump_entitlement_period_from_expires(
    *,
    tenant_id: str,
    expires_date_ms: int | None,
) -> None:
    """Align current_period_end with Apple expiresDate when present."""
    if expires_date_ms is None:
        return
    ent = entitlements_store.get(tenant_id)
    if ent.status not in {"active", "trial", "grace"}:
        return
    ent.current_period_end = float(expires_date_ms) / 1000.0
    entitlements_store.save(ent)
