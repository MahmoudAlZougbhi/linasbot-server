"""Defaults + fail-closed for Postgres cutover readiness (RC)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.billing_backend import (
    BillingBackendError,
    auth_tokens_use_postgres,
    billing_uses_postgres,
    resolve_auth_token_backend,
    resolve_billing_backend,
)
from services.meta_app_registry_bindings import resolve_meta_registry_backend


@pytest.fixture()
def clear_backend_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINAS_BILLING_BACKEND", raising=False)
    monkeypatch.delenv("LINAS_AUTH_TOKEN_BACKEND", raising=False)
    monkeypatch.delenv("META_REGISTRY_BACKEND", raising=False)


def test_defaults_resolve_to_postgres(clear_backend_env: None) -> None:
    assert resolve_billing_backend() == "postgres"
    assert resolve_auth_token_backend() == "postgres"
    assert resolve_meta_registry_backend() == "postgres"
    assert billing_uses_postgres() is True
    assert auth_tokens_use_postgres() is True


def test_file_override_still_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_BILLING_BACKEND", "file")
    monkeypatch.setenv("LINAS_AUTH_TOKEN_BACKEND", "file")
    monkeypatch.setenv("META_REGISTRY_BACKEND", "file")
    assert resolve_billing_backend() == "file"
    assert resolve_auth_token_backend() == "file"
    assert resolve_meta_registry_backend() == "file"
    assert billing_uses_postgres() is False
    assert auth_tokens_use_postgres() is False


def test_billing_fail_closed_no_file_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_BILLING_BACKEND", "postgres")
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from db.session import reset_engine_for_tests
    from services.credit_ledger_service import CreditLedgerService
    from services.entitlements_service import EntitlementsStore

    reset_engine_for_tests()
    ledger_root = tmp_path / "credit_ledger"
    ents_root = tmp_path / "entitlements"
    ledger = CreditLedgerService(root=ledger_root)
    store = EntitlementsStore(root=ents_root)
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_pg_ops.entitlements_store", store)

    with pytest.raises(BillingBackendError, match="unavailable"):
        ledger.grant_pack(tenant_id="t_fail", credits=10, request_id="r1", source="test")
    assert not any(ledger_root.glob("*"))
    assert not any(ents_root.glob("*.json"))

    with pytest.raises(BillingBackendError, match="unavailable"):
        store.save(
            store._empty("t_fail"),
        )
    assert not any(ents_root.glob("*.json"))


def test_auth_token_fail_closed_no_file_write(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_AUTH_TOKEN_BACKEND", "postgres")
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from db.session import reset_engine_for_tests
    from services.mobile_refresh_token_service import MobileRefreshTokenService

    reset_engine_for_tests()
    store_dir = tmp_path / "mobile_refresh"
    svc = MobileRefreshTokenService(store_dir=store_dir)
    with pytest.raises(BillingBackendError, match="unavailable"):
        svc.issue(user_id="u1", email="a@b.com", tenant_id="linas", session_id="s1")
    assert not any(store_dir.glob("*.json"))


def test_meta_registry_default_is_postgres(clear_backend_env: None) -> None:
    assert resolve_meta_registry_backend() == "postgres"
