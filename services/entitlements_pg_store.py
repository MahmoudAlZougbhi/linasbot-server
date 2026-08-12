"""Postgres tenant entitlements + processed-event idempotency."""

from __future__ import annotations

import time
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.credit_entitlements import EntitlementProcessedEventRow, TenantEntitlementRow


def row_to_dict(row: TenantEntitlementRow) -> dict[str, Any]:
    return {
        "tenant_id": row.tenant_id,
        "plan_id": row.plan_id,
        "status": row.status,
        "source": row.source,
        "current_period_end": row.current_period_end,
        "included_credits": int(row.included_credits or 0),
        "extra_credits": int(row.extra_credits or 0),
        "features": dict(row.features or {}),
        "updated_at": float(row.updated_at or 0),
        "store_original_transaction_id": row.store_original_transaction_id,
    }


def get_entitlement(session: Session, tenant_id: str) -> dict[str, Any] | None:
    row = session.get(TenantEntitlementRow, tenant_id)
    if row is None:
        return None
    return row_to_dict(row)


def save_entitlement(session: Session, data: dict[str, Any]) -> dict[str, Any]:
    tenant_id = str(data["tenant_id"])
    row = session.get(TenantEntitlementRow, tenant_id)
    now = float(data.get("updated_at") or time.time())
    if row is None:
        row = TenantEntitlementRow(tenant_id=tenant_id)
        session.add(row)
    row.plan_id = str(data.get("plan_id") or "none")
    row.status = str(data.get("status") or "none")
    row.source = str(data.get("source") or "none")
    row.current_period_end = data.get("current_period_end")
    row.included_credits = int(data.get("included_credits") or 0)
    row.extra_credits = int(data.get("extra_credits") or 0)
    row.features = dict(data.get("features") or {})
    row.updated_at = now
    row.store_original_transaction_id = data.get("store_original_transaction_id")
    session.flush()
    return row_to_dict(row)


def processed_event_exists(session: Session, idempotency_key: str) -> bool:
    return session.get(EntitlementProcessedEventRow, idempotency_key) is not None


def mark_processed_event(
    session: Session,
    *,
    idempotency_key: str,
    tenant_id: str,
    meta: dict[str, Any] | None = None,
) -> bool:
    """Insert processed marker. Returns False if already present."""
    if processed_event_exists(session, idempotency_key):
        return False
    try:
        with session.begin_nested():
            session.add(
                EntitlementProcessedEventRow(
                    idempotency_key=idempotency_key,
                    tenant_id=tenant_id,
                    created_at=time.time(),
                    meta=dict(meta or {"uuid": uuid.uuid4().hex}),
                )
            )
            session.flush()
        return True
    except IntegrityError:
        return False


def import_entitlement(session: Session, data: dict[str, Any]) -> bool:
    tenant_id = str(data.get("tenant_id") or "").strip()
    if not tenant_id:
        return False
    existing = session.get(TenantEntitlementRow, tenant_id)
    if existing is not None and float(existing.updated_at or 0) >= float(data.get("updated_at") or 0):
        return False
    save_entitlement(session, {**data, "tenant_id": tenant_id})
    return True


def import_processed_event(
    session: Session,
    *,
    idempotency_key: str,
    tenant_id: str,
    created_at: float,
    meta: dict[str, Any],
) -> bool:
    if session.get(EntitlementProcessedEventRow, idempotency_key) is not None:
        return False
    session.add(
        EntitlementProcessedEventRow(
            idempotency_key=idempotency_key,
            tenant_id=tenant_id,
            created_at=float(created_at or time.time()),
            meta=dict(meta),
        )
    )
    try:
        session.flush()
        return True
    except IntegrityError:
        return False
