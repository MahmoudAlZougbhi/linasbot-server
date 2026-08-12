"""Postgres SoT ledger for Apple StoreKit transactions (whatsapp_session)."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select

from db.models.apple_billing import AppleTransactionRow
from db.session import whatsapp_session
from services.apple_jws import sha256_hex
from services.iap_product_catalog import APPLE_BUNDLE_ID


def _ms(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def upsert_transaction(
    payload: dict[str, Any],
    *,
    signed_jws: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    signed_payload_sha256: str | None = None,
) -> AppleTransactionRow:
    """Insert or refresh an Apple transaction row from a decoded JWS payload."""
    tid = str(payload.get("transactionId") or "").strip()
    if not tid:
        raise ValueError("transactionId required")
    oid = str(payload.get("originalTransactionId") or tid).strip()
    product_id = str(payload.get("productId") or "").strip()
    if not product_id:
        raise ValueError("productId required")
    now = time.time()
    digest = signed_payload_sha256 or (sha256_hex(signed_jws) if signed_jws else sha256_hex(tid))
    token = payload.get("appAccountToken")
    app_account_token = str(token).strip() if token else None

    with whatsapp_session() as session:
        row = session.get(AppleTransactionRow, tid)
        if row is None:
            row = AppleTransactionRow(
                transaction_id=tid,
                original_transaction_id=oid,
                product_id=product_id,
                environment=str(payload.get("environment") or "Unknown"),
                bundle_id=str(payload.get("bundleId") or APPLE_BUNDLE_ID),
                app_account_token=app_account_token,
                tenant_id=tenant_id,
                user_id=user_id,
                purchase_date_ms=_ms(payload.get("purchaseDate")),
                expires_date_ms=_ms(payload.get("expiresDate")),
                revocation_date_ms=_ms(payload.get("revocationDate")),
                transaction_reason=(
                    str(payload.get("transactionReason")) if payload.get("transactionReason") else None
                ),
                subscription_group_id=(
                    str(payload.get("subscriptionGroupIdentifier"))
                    if payload.get("subscriptionGroupIdentifier")
                    else None
                ),
                type=str(payload.get("type") or ""),
                signed_payload_sha256=digest,
                processing_status="pending",
                first_seen_at=now,
                last_seen_at=now,
                effect={},
            )
            session.add(row)
        else:
            row.original_transaction_id = oid
            row.product_id = product_id
            row.environment = str(payload.get("environment") or row.environment)
            row.bundle_id = str(payload.get("bundleId") or row.bundle_id)
            if app_account_token:
                row.app_account_token = app_account_token
            if tenant_id and not row.tenant_id:
                row.tenant_id = tenant_id
            elif tenant_id and row.tenant_id and row.tenant_id != tenant_id:
                raise PermissionError("transaction already bound to a different tenant")
            if user_id and not row.user_id:
                row.user_id = user_id
            elif user_id and row.user_id and row.user_id != user_id:
                # Keep original owner; do not silently rebind.
                pass
            row.purchase_date_ms = _ms(payload.get("purchaseDate")) or row.purchase_date_ms
            row.expires_date_ms = _ms(payload.get("expiresDate"))
            row.revocation_date_ms = _ms(payload.get("revocationDate"))
            if payload.get("transactionReason") is not None:
                row.transaction_reason = str(payload.get("transactionReason"))
            if payload.get("subscriptionGroupIdentifier") is not None:
                row.subscription_group_id = str(payload.get("subscriptionGroupIdentifier"))
            if payload.get("type"):
                row.type = str(payload.get("type"))
            row.signed_payload_sha256 = digest
            row.last_seen_at = now
        session.flush()
        session.expunge(row)
        return row


def mark_applied(transaction_id: str, effect: dict[str, Any] | None = None) -> AppleTransactionRow:
    tid = str(transaction_id or "").strip()
    with whatsapp_session() as session:
        row = session.get(AppleTransactionRow, tid)
        if row is None:
            raise ValueError(f"unknown transaction: {tid}")
        if row.processing_status == "applied":
            session.expunge(row)
            return row
        row.processing_status = "applied"
        row.last_seen_at = time.time()
        if effect:
            merged = dict(row.effect or {})
            merged.update(effect)
            row.effect = merged
        session.flush()
        session.expunge(row)
        return row


def mark_reversed(transaction_id: str, effect: dict[str, Any] | None = None) -> AppleTransactionRow:
    tid = str(transaction_id or "").strip()
    with whatsapp_session() as session:
        row = session.get(AppleTransactionRow, tid)
        if row is None:
            raise ValueError(f"unknown transaction: {tid}")
        if row.processing_status == "reversed":
            session.expunge(row)
            return row
        row.processing_status = "reversed"
        row.last_seen_at = time.time()
        if effect:
            merged = dict(row.effect or {})
            merged.update(effect)
            row.effect = merged
        session.flush()
        session.expunge(row)
        return row


def get_by_transaction_id(transaction_id: str) -> AppleTransactionRow | None:
    tid = str(transaction_id or "").strip()
    if not tid:
        return None
    with whatsapp_session() as session:
        row = session.get(AppleTransactionRow, tid)
        if row is not None:
            session.expunge(row)
        return row


def list_by_original_transaction_id(original_transaction_id: str) -> list[AppleTransactionRow]:
    oid = str(original_transaction_id or "").strip()
    if not oid:
        return []
    with whatsapp_session() as session:
        rows = list(
            session.scalars(
                select(AppleTransactionRow)
                .where(AppleTransactionRow.original_transaction_id == oid)
                .order_by(AppleTransactionRow.first_seen_at.asc())
            )
        )
        for row in rows:
            session.expunge(row)
        return rows
