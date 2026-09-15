"""Tests for dual input/output wallet, public pricing hygiene, analytics, AI limits."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from services.ai_setup.ai_usage_limits import (
    RECOMMENDED_CONTEXT_LINES_PER_DAY,
    RECOMMENDED_IMAGE_PER_WEEK,
    AiUsageLimitsService,
    day_period_key,
    recommended_defaults,
    week_period_key,
)
from services.billing.token_metering import assert_tenant_can_use_ai, debit_ai_usage
from services.billing.token_package_catalog import (
    assert_public_payload_has_no_internal_economics,
    build_package,
    catalog_public_payload,
    list_token_packages,
)
from services.billing.wallet_spend_analytics import build_wallet_spend_analytics


@pytest.fixture()
def limits_svc(tmp_path: Path) -> AiUsageLimitsService:
    return AiUsageLimitsService(store_dir=tmp_path / "ai_limits")


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
    pricing = (
        Path(__file__).resolve().parents[1]
        / "dashboard"
        / "src"
        / "components"
        / "landing"
        / "sections"
        / "LandingPricing.jsx"
    )
    text = pricing.read_text(encoding="utf-8")
    assert 'id="pricing"' in text
    assert "30% profit" not in text
    assert "OpenAI cost" not in text
    # Cost-model jargon stays off the marketing landing; live amounts come from public plans.
    assert "input tokens" not in text
    assert "output tokens" not in text
    assert "/api/public/plans" in text
    assert "/api/billing/packages" not in text


def test_settings_wallet_removed_and_ai_limits_in_cm() -> None:
    root = Path(__file__).resolve().parents[1]
    dashboard_src = root / "dashboard" / "src"
    # Web Settings / CM pages are gone; leftover wallet/settings HTTP must not be called.
    assert not (dashboard_src / "pages" / "Settings.jsx").is_file()
    texts: list[str] = []
    for pattern in ("*.js", "*.jsx"):
        texts.extend(p.read_text(encoding="utf-8") for p in dashboard_src.rglob(pattern) if p.is_file())
    blob = "\n".join(texts)
    assert "/api/billing/wallet" not in blob
    assert "/api/billing/packages" not in blob
    assert "/api/settings" not in blob


def test_preflight_uses_credit_gate_not_token_wallet(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.billing.membership.generative_gate.generative_ai_blocked",
        lambda *_a, **_k: True,
    )
    with pytest.raises(PermissionError):
        assert_tenant_can_use_ai("newbiz")
    monkeypatch.setattr(
        "services.billing.membership.generative_gate.generative_ai_blocked",
        lambda *_a, **_k: False,
    )
    assert_tenant_can_use_ai("newbiz")


def test_ai_preflight_does_not_treat_linas_as_unlimited(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", "linas")
    monkeypatch.setattr(
        "services.billing.membership.generative_gate.generative_ai_blocked",
        lambda *_a, **_k: True,
    )
    with pytest.raises(PermissionError):
        assert_tenant_can_use_ai("linas")
    assert debit_ai_usage(tenant_id="linas", prompt_tokens=50, completion_tokens=10, model="gpt-5.1") is None


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
