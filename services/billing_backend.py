"""Explicit backend resolution for billing + auth token persistence.

Env flags (default file for safety until HA cutover):
  - LINAS_BILLING_BACKEND=file|postgres
  - LINAS_AUTH_TOKEN_BACKEND=file|postgres

Residual file-only in this pass:
  - credit_ledger_service (balances/reservations/capture)
  - entitlements_store

Token wallets, Stripe webhook idempotency, admin credit idempotency, mobile
refresh tokens, and auth email tokens are PG-capable when flags are set.
"""

from __future__ import annotations

import os
from typing import Literal, cast

BillingBackend = Literal["file", "postgres"]
AuthTokenBackend = Literal["file", "postgres"]


class BillingBackendError(RuntimeError):
    pass


def resolve_billing_backend() -> BillingBackend:
    raw = (os.getenv("LINAS_BILLING_BACKEND") or "file").strip().lower()
    if raw not in {"file", "postgres"}:
        raise BillingBackendError("LINAS_BILLING_BACKEND must be file|postgres")
    return cast(BillingBackend, raw)


def resolve_auth_token_backend() -> AuthTokenBackend:
    raw = (os.getenv("LINAS_AUTH_TOKEN_BACKEND") or "file").strip().lower()
    if raw not in {"file", "postgres"}:
        raise BillingBackendError("LINAS_AUTH_TOKEN_BACKEND must be file|postgres")
    return cast(AuthTokenBackend, raw)


def billing_uses_postgres() -> bool:
    return resolve_billing_backend() == "postgres"


def auth_tokens_use_postgres() -> bool:
    return resolve_auth_token_backend() == "postgres"
