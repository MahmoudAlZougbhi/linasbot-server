"""Direct tests for token wallet model helpers (tenant normalization)."""

from __future__ import annotations

import pytest

from services.token_wallet_models import (
    is_unlimited_tenant,
    normalize_wallet_tenant_id,
    unlimited_tenant_ids,
)


def test_unlimited_tenant_ids_env_default_is_linas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", raising=False)
    assert unlimited_tenant_ids() == frozenset({"linas"})


@pytest.mark.parametrize("tenant_id", [None, "", "   ", "\t"])
def test_normalize_wallet_tenant_id_rejects_missing(tenant_id: str | None) -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        normalize_wallet_tenant_id(tenant_id)


def test_normalize_wallet_tenant_id_strips_and_lowercases() -> None:
    assert normalize_wallet_tenant_id("  AcMe-Co  ") == "acme-co"


def test_is_unlimited_tenant_explicit_linas(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", "linas")
    assert is_unlimited_tenant("linas") is True
    assert is_unlimited_tenant("acme-co") is False


@pytest.mark.parametrize("tenant_id", [None, "", "   "])
def test_is_unlimited_tenant_rejects_missing(tenant_id: str | None) -> None:
    with pytest.raises(ValueError, match="tenant_id required"):
        is_unlimited_tenant(tenant_id)
