"""Explicit backend resolution for billing + auth token persistence.

Production-cutover-ready defaults (RC):
  - LINAS_BILLING_BACKEND=postgres  (override with ``file`` for local/dev)
  - LINAS_AUTH_TOKEN_BACKEND=postgres  (override with ``file`` for local/dev)

When LINAS_BILLING_BACKEND=postgres:
  - token wallets + wallet ledger
  - Stripe / admin-credit idempotency
  - credit_ledger balances + entries
  - tenant entitlements + processed-event idempotency
  Fail closed if Postgres is unavailable — never silently use file SoT.

When LINAS_AUTH_TOKEN_BACKEND=postgres:
  - mobile refresh tokens
  - auth email tokens
  Fail closed if Postgres is unavailable — never silently use file SoT.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import TYPE_CHECKING, Literal, cast

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

BillingBackend = Literal["file", "postgres"]
AuthTokenBackend = Literal["file", "postgres"]


class BillingBackendError(RuntimeError):
    """Honest fail-closed error for billing/auth Postgres SoT."""

    pass


def resolve_billing_backend() -> BillingBackend:
    raw = (os.getenv("LINAS_BILLING_BACKEND") or "postgres").strip().lower()
    if raw not in {"file", "postgres"}:
        raise BillingBackendError("LINAS_BILLING_BACKEND must be file|postgres")
    return cast(BillingBackend, raw)


def resolve_auth_token_backend() -> AuthTokenBackend:
    raw = (os.getenv("LINAS_AUTH_TOKEN_BACKEND") or "postgres").strip().lower()
    if raw not in {"file", "postgres"}:
        raise BillingBackendError("LINAS_AUTH_TOKEN_BACKEND must be file|postgres")
    return cast(AuthTokenBackend, raw)


def billing_uses_postgres() -> bool:
    return resolve_billing_backend() == "postgres"


def auth_tokens_use_postgres() -> bool:
    return resolve_auth_token_backend() == "postgres"


@contextmanager
def require_billing_pg_session() -> Iterator[Session]:
    """Postgres session for billing SoT. Never falls back to file."""
    if not billing_uses_postgres():
        raise BillingBackendError("Billing Postgres session requested but LINAS_BILLING_BACKEND is not postgres")
    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

    try:
        with whatsapp_session(require=True) as session:
            yield session
    except WhatsAppDatabaseUnavailable as exc:
        raise BillingBackendError(
            "Billing Postgres backend is unavailable (LINAS_BILLING_BACKEND=postgres). File SoT is not a live fallback."
        ) from exc


@contextmanager
def require_auth_token_pg_session() -> Iterator[Session]:
    """Postgres session for auth-token SoT. Never falls back to file."""
    if not auth_tokens_use_postgres():
        raise BillingBackendError("Auth-token Postgres session requested but LINAS_AUTH_TOKEN_BACKEND is not postgres")
    from db.session import WhatsAppDatabaseUnavailable, whatsapp_session

    try:
        with whatsapp_session(require=True) as session:
            yield session
    except WhatsAppDatabaseUnavailable as exc:
        raise BillingBackendError(
            "Auth-token Postgres backend is unavailable (LINAS_AUTH_TOKEN_BACKEND=postgres). "
            "File SoT is not a live fallback."
        ) from exc
