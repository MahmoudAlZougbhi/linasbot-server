"""Tests for SaaS auth email flows, dual input/output token packages, and wallet metering."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from modules.api_security import is_public_api
from services.auth_email_tokens import AuthEmailTokenService
from services.token_metering import assert_tenant_can_use_ai
from services.token_package_catalog import (
    assert_public_payload_has_no_internal_economics,
    build_package,
    catalog_public_payload,
    list_token_packages,
)
from services.token_wallet_service import InsufficientTokenBalance, TokenWalletService, is_unlimited_tenant


@pytest.fixture()
def wallet_svc(tmp_path: Path) -> TokenWalletService:
    return TokenWalletService(store_dir=tmp_path / "wallets")


@pytest.fixture()
def token_svc(tmp_path: Path) -> AuthEmailTokenService:
    return AuthEmailTokenService(store_dir=tmp_path / "tokens")


@pytest.fixture(scope="module")
def app_client() -> TestClient:
    import main  # noqa: F401
    from modules.core import app

    return TestClient(app)


def test_auth_email_routes_are_public() -> None:
    assert is_public_api("POST", "/api/auth/forgot-password")
    assert is_public_api("POST", "/api/auth/reset-password")
    assert is_public_api("POST", "/api/auth/verify-email")
    assert is_public_api("POST", "/api/auth/resend-verification")
    assert is_public_api("GET", "/api/billing/packages")
    assert is_public_api("GET", "/api/public/plans")
    assert is_public_api("POST", "/api/billing/stripe/webhook")


def test_forgot_password_does_not_reveal_missing_email(app_client: TestClient) -> None:
    with mock.patch("services.user_service.user_service.get_user_by_email", return_value=None):
        response = app_client.post("/api/auth/forgot-password", json={"email": "nobody@example.com"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert "If an account exists" in payload["message"]


def test_password_reset_token_roundtrip(token_svc: AuthEmailTokenService) -> None:
    raw = token_svc.issue(
        purpose="password_reset",
        user_id="u1",
        email="a@example.com",
        tenant_id="acme",
        ttl_seconds=600,
    )
    peeked = token_svc.peek(raw, "password_reset")
    assert peeked is not None
    assert peeked.user_id == "u1"
    consumed = token_svc.consume(raw, "password_reset")
    assert consumed is not None
    assert token_svc.consume(raw, "password_reset") is None


def test_email_verify_token_single_use(token_svc: AuthEmailTokenService) -> None:
    raw = token_svc.issue(
        purpose="email_verify",
        user_id="u2",
        email="b@example.com",
        tenant_id="acme",
    )
    assert token_svc.consume(raw, "email_verify") is not None
    assert token_svc.consume(raw, "email_verify") is None


def test_package_catalog_has_six_skus_and_thirty_percent_margin() -> None:
    packages = list_token_packages()
    assert len(packages) == 6
    for pack in packages:
        assert 29.0 <= pack.margin_pct <= 31.0
        assert pack.input_tokens > 0
        assert pack.output_tokens > 0
        assert pack.sell_price_usd > 0
    mid = build_package(1_000_000, 1_000_000)
    assert mid.openai_cost_usd == pytest.approx(11.25, rel=1e-6)
    assert mid.sell_price_usd == 14.63


def test_public_packages_endpoint() -> None:
    payload = catalog_public_payload()
    assert payload["success"] is True
    assert len(payload["packages"]) == 6
    assert_public_payload_has_no_internal_economics(payload)
    assert "profit_multiplier" not in payload
    assert "30%" not in str(payload).lower()
    for pack in payload["packages"]:
        assert "input_tokens" in pack
        assert "output_tokens" in pack


def test_landing_pricing_section_in_source() -> None:
    root = Path(__file__).resolve().parents[1]
    landing = root / "dashboard" / "src" / "pages" / "public" / "Landing.jsx"
    pricing = root / "dashboard" / "src" / "components" / "landing" / "sections" / "LandingPricing.jsx"
    landing_text = landing.read_text(encoding="utf-8")
    pricing_text = pricing.read_text(encoding="utf-8")
    # Design ZIP moved the pricing section into LandingPricing; Landing composes it.
    assert "LandingPricing" in landing_text
    assert 'id="pricing"' in pricing_text
    # Marketing pricing preview points to in-app billing catalog (no wallet packages fetch).
    assert "billing catalog" in pricing_text.lower()
    assert "app" in pricing_text.lower()
    assert "/api/billing/packages" not in pricing_text
    assert "/api/billing/packages" not in landing_text
    assert "30% profit" not in pricing_text


def test_unlimited_linas_bypass(wallet_svc: TokenWalletService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", "linas")
    assert is_unlimited_tenant("linas")
    assert not is_unlimited_tenant("acme-co")
    assert_tenant_can_use_ai("linas")  # does not raise even at zero
    with pytest.raises(InsufficientTokenBalance):
        assert_tenant_can_use_ai("acme-co")


def test_wallet_credit_debit_atomic_no_negative(wallet_svc: TokenWalletService) -> None:
    wallet_svc.credit("acme", input_tokens=800, output_tokens=200, amount_usd=3.9, reason="test")
    snap = wallet_svc.debit("acme", prompt_tokens=300, completion_tokens=100, cost_usd=0.01)
    assert snap.input_remaining == 500
    assert snap.output_remaining == 100
    with pytest.raises(InsufficientTokenBalance):
        wallet_svc.debit("acme", prompt_tokens=501, completion_tokens=1)
    assert wallet_svc.get_wallet("acme").input_remaining == 500


def test_zero_balance_blocks_ai_gate(wallet_svc: TokenWalletService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.token_metering.token_wallet_service", wallet_svc)
    monkeypatch.setattr("services.token_wallet_service.token_wallet_service", wallet_svc)
    with pytest.raises(InsufficientTokenBalance):
        assert_tenant_can_use_ai("newbiz")
    wallet_svc.credit("newbiz", input_tokens=10, output_tokens=10, reason="seed")
    assert_tenant_can_use_ai("newbiz")


def test_catalog_public_payload_shape() -> None:
    payload = catalog_public_payload()
    assert "packages" in payload
    assert "summary" in payload
    assert "profit_multiplier" not in payload
    assert "orchestration_model" not in payload
    assert_public_payload_has_no_internal_economics(payload)
