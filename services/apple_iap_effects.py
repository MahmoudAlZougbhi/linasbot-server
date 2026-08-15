"""Apple IAP side-effects: subscription entitlements + consumable credit grants."""

from __future__ import annotations

import time
from typing import Any

from db.models.apple_billing import AppleAppAccountTokenRow
from db.session import whatsapp_session
from services.apple_credit_grant_ops import (  # noqa: F401 — re-export for callers
    grant_consumable_credits,
    reverse_consumable_credits,
)
from services.entitlements_service import EntitlementStatus, apply_store_notification, entitlements_store
from services.iap_product_catalog import (
    is_credit_product,
    is_subscription_product,
    map_subscription_product,
)
from services.store_iap_service import normalize_apple_status
from services.subscription_downgrade import (
    clear_pending_downgrade,
    schedule_pending_downgrade,
    should_schedule_instead_of_apply,
)


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
    notification_type: str | None = None,
) -> dict[str, Any]:
    plan_id = map_subscription_product(product_id)
    existing = entitlements_store.get(tenant_id)
    if should_schedule_instead_of_apply(
        current_plan_id=existing.plan_id,
        target_plan_id=plan_id,
        status=status,
        notification_type=notification_type,
    ):
        scheduled = schedule_pending_downgrade(
            tenant_id=tenant_id,
            pending_plan_id=plan_id,
            effective_at=existing.current_period_end,
        )
        return {
            "kind": "subscription",
            "plan_id": plan_id,
            "status": status,
            "scheduled_downgrade": True,
            "pending_downgrade": scheduled,
            "duplicate": False,
        }

    if status == "active":
        clear_pending_downgrade(tenant_id)

    result = apply_store_notification(
        tenant_id=tenant_id,
        plan_id=plan_id,  # type: ignore[arg-type]
        status=status,
        source="apple",
        original_transaction_id=original_transaction_id,
        idempotency_key=idempotency_key,
        force_apply=True,
    )
    return {"kind": "subscription", "plan_id": plan_id, "status": status, **result}


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
