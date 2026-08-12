"""Postgres billing helpers: Stripe idempotency + admin credit idempotency."""

from __future__ import annotations

import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db.models.billing_auth import AdminCreditIdempotencyRow, StripeProcessedEventRow


def stripe_already_processed(session: Session, event_id: str) -> bool:
    return session.get(StripeProcessedEventRow, event_id) is not None


def stripe_mark_processed(session: Session, event_id: str, meta: dict[str, Any]) -> bool:
    """Insert event row. Returns False when already processed (unique violation)."""
    if stripe_already_processed(session, event_id):
        return False
    try:
        with session.begin_nested():
            session.add(
                StripeProcessedEventRow(
                    event_id=event_id,
                    created_at=time.time(),
                    meta=dict(meta),
                )
            )
            session.flush()
        return True
    except IntegrityError:
        return False


def admin_credit_load(session: Session, key: str) -> dict[str, Any] | None:
    row = session.get(AdminCreditIdempotencyRow, key)
    if row is None:
        return None
    meta = dict(row.meta or {})
    if isinstance(meta.get("response"), dict):
        return meta
    return None


def admin_credit_store(session: Session, key: str, response: dict[str, Any]) -> None:
    row = session.get(AdminCreditIdempotencyRow, key)
    payload = {"idempotency_key": key, "ts": time.time(), "response": response}
    if row is None:
        session.add(
            AdminCreditIdempotencyRow(
                key=key,
                created_at=time.time(),
                meta=payload,
            )
        )
    else:
        row.meta = payload
        row.created_at = time.time()
    session.flush()


def import_stripe_event(session: Session, event_id: str, created_at: float, meta: dict[str, Any]) -> bool:
    if session.get(StripeProcessedEventRow, event_id) is not None:
        return False
    session.add(
        StripeProcessedEventRow(
            event_id=event_id,
            created_at=created_at,
            meta=dict(meta),
        )
    )
    try:
        session.flush()
        return True
    except IntegrityError:
        session.rollback()
        return False


def import_admin_credit_key(session: Session, key: str, created_at: float, meta: dict[str, Any]) -> bool:
    if session.get(AdminCreditIdempotencyRow, key) is not None:
        return False
    session.add(
        AdminCreditIdempotencyRow(
            key=key,
            created_at=created_at,
            meta=dict(meta),
        )
    )
    try:
        session.flush()
        return True
    except IntegrityError:
        session.rollback()
        return False


def list_stripe_event_ids(session: Session) -> set[str]:
    return set(session.scalars(select(StripeProcessedEventRow.event_id)).all())
