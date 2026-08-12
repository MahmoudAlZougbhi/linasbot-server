"""Postgres backend tests for billing wallets, Stripe idempotency, and auth tokens."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.admin_credit_idempotency import (  # noqa: E402
    load_admin_credit_idempotent,
    store_admin_credit_idempotent,
)
from services.auth_email_tokens import AuthEmailTokenService  # noqa: E402
from services.mobile_refresh_token_service import MobileRefreshTokenService  # noqa: E402
from services.stripe_checkout_service import StripeCheckoutService  # noqa: E402
from services.token_wallet_service import InsufficientTokenBalance, TokenWalletService  # noqa: E402


@pytest.fixture()
def pg_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    url = f"sqlite:///{tmp_path / 'billing_auth.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    monkeypatch.setenv("LINAS_BILLING_BACKEND", "postgres")
    monkeypatch.setenv("LINAS_AUTH_TOKEN_BACKEND", "postgres")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()


def test_wallet_credit_debit_transactional(pg_env: Path) -> None:
    svc = TokenWalletService(store_dir=pg_env / "wallets")
    svc.credit("tenant-a", input_tokens=100, output_tokens=50, reason="test_seed")
    snap = svc.debit("tenant-a", prompt_tokens=10, completion_tokens=5, reason="ai_usage")
    assert snap.input_remaining == 90
    assert snap.output_remaining == 45
    ledger = svc.recent_ledger("tenant-a", limit=10)
    assert any(row.get("type") == "credit" for row in ledger)
    assert any(row.get("type") == "debit" for row in ledger)
    with pytest.raises(InsufficientTokenBalance):
        svc.debit("tenant-a", prompt_tokens=10_000, completion_tokens=0)


def test_stripe_event_idempotency_unique(pg_env: Path) -> None:
    stripe = StripeCheckoutService(processed_dir=pg_env / "stripe_events")
    assert stripe.already_processed("evt_test_1") is False
    stripe.mark_processed("evt_test_1", {"tenant_id": "t1"})
    assert stripe.already_processed("evt_test_1") is True
    stripe.mark_processed("evt_test_1", {"tenant_id": "t1"})
    assert stripe.already_processed("evt_test_1") is True

    from db.models.billing_auth import StripeProcessedEventRow

    with whatsapp_session() as session:
        with session.begin_nested():
            session.add(
                StripeProcessedEventRow(
                    event_id="evt_dup",
                    created_at=1.0,
                    meta={"x": 1},
                )
            )
            session.flush()
        with pytest.raises(IntegrityError):
            with session.begin_nested():
                session.add(
                    StripeProcessedEventRow(
                        event_id="evt_dup",
                        created_at=2.0,
                        meta={"x": 2},
                    )
                )
                session.flush()


def test_mobile_refresh_issue_consume(pg_env: Path) -> None:
    svc = MobileRefreshTokenService(store_dir=pg_env / "mobile_refresh")
    raw = svc.issue(user_id="u1", email="a@b.com", tenant_id="linas", session_id="s1")
    rec = svc.consume(raw)
    assert rec is not None
    assert rec.tenant_id == "linas"
    assert svc.consume(raw) is None


def test_email_token_issue_consume(pg_env: Path) -> None:
    svc = AuthEmailTokenService(store_dir=pg_env / "email_tokens")
    raw = svc.issue(
        purpose="password_reset",
        user_id="u1",
        email="a@b.com",
        tenant_id="acme",
        ttl_seconds=600,
    )
    peeked = svc.peek(raw, "password_reset")
    assert peeked is not None
    consumed = svc.consume(raw, "password_reset")
    assert consumed is not None
    assert svc.consume(raw, "password_reset") is None


def test_admin_credit_idempotency_pg(pg_env: Path) -> None:
    payload = {"success": True, "wallet": {"tenant_id": "t1"}}
    store_admin_credit_idempotent("idem-key-12345678", payload)
    cached = load_admin_credit_idempotent("idem-key-12345678")
    assert cached is not None
    assert cached.get("response") == payload
