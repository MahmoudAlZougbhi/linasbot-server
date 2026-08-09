"""Tests for dual input/output wallet, public pricing hygiene, analytics, AI limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.ai_usage_limits import (
    RECOMMENDED_CONTEXT_LINES_PER_DAY,
    RECOMMENDED_IMAGE_PER_WEEK,
    AiUsageLimitsService,
    day_period_key,
    recommended_defaults,
    week_period_key,
)
from services.token_metering import assert_tenant_can_use_ai, debit_ai_usage
from services.token_package_catalog import (
    assert_public_payload_has_no_internal_economics,
    build_package,
    catalog_public_payload,
    list_token_packages,
)
from services.token_wallet_service import InsufficientTokenBalance, TokenWalletService
from services.wallet_spend_analytics import build_wallet_spend_analytics


@pytest.fixture()
def wallet_svc(tmp_path: Path) -> TokenWalletService:
    return TokenWalletService(store_dir=tmp_path / "wallets")


@pytest.fixture()
def limits_svc(tmp_path: Path) -> AiUsageLimitsService:
    return AiUsageLimitsService(store_dir=tmp_path / "ai_limits")


@pytest.fixture(scope="module")
def app_client() -> TestClient:
    import main  # noqa: F401
    from modules.core import app

    return TestClient(app)


def test_six_packages_have_input_and_output_allotments() -> None:
    packages = list_token_packages()
    assert len(packages) == 6
    for pack in packages:
        assert pack.input_tokens > 0
        assert pack.output_tokens > 0
        assert 29.0 <= pack.margin_pct <= 31.0
        public = pack.to_public_dict()
        assert "input_tokens" in public
        assert "output_tokens" in public
        assert "margin_pct" not in public
        assert "openai_cost_usd" not in public


def test_one_million_equal_pack_sell_price() -> None:
    """Owner-shaped example: 1M input + 1M output priced from gpt-5.1 × 1.30."""
    pack = build_package(1_000_000, 1_000_000)
    # cost_in=1.25, cost_out=10.0 → 11.25 × 1.30 = 14.625 → 14.63
    assert pack.openai_cost_usd == pytest.approx(11.25, rel=1e-6)
    assert pack.sell_price_usd == 14.63
    assert pack.id == "pack_in1000000_out1000000"


def test_public_catalog_omits_margin_and_shows_dual_allotments() -> None:
    payload = catalog_public_payload()
    assert_public_payload_has_no_internal_economics(payload)
    assert "profit_multiplier" not in payload
    assert "basis" not in payload
    assert "pricing_model" not in payload
    assert len(payload["packages"]) == 6
    for pack in payload["packages"]:
        assert pack["input_tokens"] > 0
        assert pack["output_tokens"] > 0
        assert "sell_price_usd" in pack


def test_landing_pricing_has_no_profit_copy() -> None:
    landing = Path(__file__).resolve().parents[1] / "dashboard" / "src" / "pages" / "public" / "Landing.jsx"
    text = landing.read_text(encoding="utf-8")
    assert 'id="pricing"' in text
    assert "30% profit" not in text
    assert "OpenAI cost" not in text
    # Cost-model jargon stays off the marketing landing; billing detail lives in-app / pricing page.
    assert "input tokens" not in text
    assert "output tokens" not in text
    assert "Subscriptions and usage credits are managed in the Linas AI mobile app" in text


def test_settings_wallet_removed_and_ai_limits_in_cm() -> None:
    root = Path(__file__).resolve().parents[1]
    settings = root / "dashboard" / "src" / "pages" / "Settings.jsx"
    cm_limits = root / "dashboard" / "src" / "pages" / "content-managers" / "CmAiLimitsPage.jsx"
    text = settings.read_text(encoding="utf-8")
    # Token Wallet lives in the sidebar nav, not inside Settings tabs.
    assert "id: 'wallet'" not in text
    assert "Token Wallet" not in text
    assert "id: 'api'" not in text
    assert "Human Takeover" not in text
    assert "System language" in text
    # AI Limits live in Content Managers (not Settings tabs) for SaaS self-service.
    assert "ai-limits" not in text
    assert "AiLimitsPanel" not in text
    assert cm_limits.is_file()
    limits_text = cm_limits.read_text(encoding="utf-8")
    assert "ai_limits" in limits_text
    assert "voice_processing_enabled" in limits_text
    assert "image_analysis_enabled" in limits_text


def test_dual_balance_credit_debit(wallet_svc: TokenWalletService) -> None:
    wallet_svc.credit("acme", input_tokens=1000, output_tokens=500, amount_usd=5.0, reason="test")
    snap = wallet_svc.get_wallet("acme")
    assert snap.input_remaining == 1000
    assert snap.output_remaining == 500
    snap = wallet_svc.debit("acme", prompt_tokens=200, completion_tokens=50, cost_usd=0.01)
    assert snap.input_remaining == 800
    assert snap.output_remaining == 450
    with pytest.raises(InsufficientTokenBalance) as exc:
        wallet_svc.debit("acme", prompt_tokens=801, completion_tokens=1)
    assert exc.value.bucket == "input"
    assert wallet_svc.get_wallet("acme").input_remaining == 800


def test_preflight_requires_both_buckets(wallet_svc: TokenWalletService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.token_metering.token_wallet_service", wallet_svc)
    monkeypatch.setattr("services.token_wallet_service.token_wallet_service", wallet_svc)
    monkeypatch.setenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", "linas")
    with pytest.raises(InsufficientTokenBalance):
        assert_tenant_can_use_ai("newbiz")
    wallet_svc.credit("newbiz", input_tokens=10, output_tokens=0, reason="partial")
    with pytest.raises(InsufficientTokenBalance) as exc:
        assert_tenant_can_use_ai("newbiz")
    assert exc.value.bucket == "output"
    wallet_svc.credit("newbiz", input_tokens=0, output_tokens=10, reason="fill_output")
    assert_tenant_can_use_ai("newbiz")


def test_debit_ai_usage_splits_prompt_completion(
    wallet_svc: TokenWalletService, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("services.token_metering.token_wallet_service", wallet_svc)
    wallet_svc.credit("metered", input_tokens=500, output_tokens=200, reason="seed")
    debit_ai_usage(tenant_id="metered", prompt_tokens=100, completion_tokens=40, model="gpt-5.1")
    snap = wallet_svc.get_wallet("metered")
    assert snap.input_remaining == 400
    assert snap.output_remaining == 160


def test_legacy_balance_migrates_80_20(wallet_svc: TokenWalletService) -> None:
    path = wallet_svc._wallet_path("legacyco")
    path.write_text(
        '{"tenant_id":"legacyco","balance_tokens":1000,"lifetime_credited":1000,'
        '"lifetime_debited":0,"lifetime_spent_usd":3.0,"updated_at":1}',
        encoding="utf-8",
    )
    snap = wallet_svc.get_wallet("legacyco")
    assert snap.input_remaining == 800
    assert snap.output_remaining == 200
    assert snap.migrated_from_legacy is True
    # Second read stays stable.
    snap2 = wallet_svc.get_wallet("legacyco")
    assert snap2.input_remaining == 800
    assert snap2.output_remaining == 200


def test_unlimited_linas_unchanged(wallet_svc: TokenWalletService, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", "linas")
    monkeypatch.setattr("services.token_metering.token_wallet_service", wallet_svc)
    assert_tenant_can_use_ai("linas")
    debit_ai_usage(tenant_id="linas", prompt_tokens=50, completion_tokens=10, model="gpt-5.1")


def test_spend_analytics_fb_ig_and_top_conversation() -> None:
    now = datetime.now(UTC)
    entries = [
        {
            "timestamp": now.isoformat().replace("+00:00", "Z"),
            "tenant_id": "acme",
            "channel": "facebook",
            "conversation_id": "c-fb-1",
            "tokens": 100,
            "prompt_tokens": 80,
            "completion_tokens": 20,
            "cost_usd": 0.05,
        },
        {
            "timestamp": now.isoformat().replace("+00:00", "Z"),
            "tenant_id": "acme",
            "channel": "instagram",
            "conversation_id": "c-ig-hot",
            "tokens": 500,
            "prompt_tokens": 400,
            "completion_tokens": 100,
            "cost_usd": 0.40,
        },
        {
            "timestamp": now.isoformat().replace("+00:00", "Z"),
            "tenant_id": "acme",
            "channel": "instagram",
            "conversation_id": "c-ig-hot",
            "tokens": 200,
            "cost_usd": 0.10,
        },
        {
            "timestamp": (now - timedelta(days=400)).isoformat().replace("+00:00", "Z"),
            "tenant_id": "acme",
            "channel": "facebook",
            "conversation_id": "old",
            "tokens": 50,
            "cost_usd": 0.01,
        },
    ]
    result = build_wallet_spend_analytics("acme", entries=entries)
    trailing = result["periods"]["trailing_12_months"]
    assert trailing["by_channel"]["facebook"]["interactions"] == 1
    assert trailing["by_channel"]["instagram"]["interactions"] == 2
    assert trailing["top_conversations"][0]["conversation_id"] == "c-ig-hot"
    prior = result["periods"]["prior_12_months"]
    assert prior["by_channel"]["facebook"]["interactions"] == 1


def test_ai_limits_day_week_caps_and_defaults(limits_svc: AiUsageLimitsService) -> None:
    defaults = recommended_defaults()
    assert defaults["image_per_week"] == RECOMMENDED_IMAGE_PER_WEEK
    assert defaults["context_lines_per_day"] == RECOMMENDED_CONTEXT_LINES_PER_DAY
    assert defaults["unlimited"] is False

    limits_svc.save_settings("clinic-a", {"image_per_day": 2, "image_per_week": 3})
    d1 = limits_svc.consume_images("clinic-a", "user-1", amount=1)
    assert d1.allowed
    d2 = limits_svc.consume_images("clinic-a", "user-1", amount=1)
    assert d2.allowed
    d3 = limits_svc.consume_images("clinic-a", "user-1", amount=1)
    assert not d3.allowed
    assert d3.reason == "image_day_limit"

    # Different end-user has independent quota.
    other = limits_svc.consume_images("clinic-a", "user-2", amount=1)
    assert other.allowed

    # Week boundary key format.
    assert day_period_key().startswith("day:")
    assert "W" in week_period_key()


def test_ai_limits_unlimited_toggle(limits_svc: AiUsageLimitsService) -> None:
    limits_svc.save_settings("clinic-b", {"image_per_day": 1, "unlimited": True})
    for _ in range(5):
        assert limits_svc.consume_images("clinic-b", "heavy", amount=1).allowed


def test_context_line_truncation(limits_svc: AiUsageLimitsService) -> None:
    limits_svc.save_settings("clinic-c", {"context_lines_per_day": 3, "context_lines_per_week": 100})
    text = "a\nb\nc\nd\ne\n"
    decision = limits_svc.check_context_line_quota("clinic-c", "u1", amount=5)
    assert decision.allowed_amount == 3
    truncated = limits_svc.truncate_text_to_line_budget(text, 3)
    assert truncated.count("\n") >= 2
    assert "d" not in truncated.splitlines() or truncated.splitlines().count("d") == 0
    kept_nonempty = [ln for ln in truncated.splitlines() if ln.strip()]
    assert len(kept_nonempty) == 3
