"""Catalog SoT revenue vs live checkout, and cost-environment honesty."""

from __future__ import annotations

import pytest

from services.membership.catalog_revenue import intended_price_usd, live_checkout_mrr, revenue_pair
from services.membership.cost_dashboard import global_dashboard
from services.membership.expense_journal import expense_environment, record_expense, reset_expenses_for_tests
from services.plan_economics import PLAN_PRICES_USD


@pytest.fixture(autouse=True)
def _clean() -> None:
    reset_expenses_for_tests()


def test_intended_message_price_is_catalog_not_credit() -> None:
    assert intended_price_usd("lite") == 10.0
    assert PLAN_PRICES_USD["lite"] != 10.0
    pair = revenue_pair(["lite", "starter"])
    assert pair["intended_message_mrr_usd"] == 39.0
    assert pair["live_checkout_mrr_usd"] == live_checkout_mrr(["lite", "starter"])
    assert pair["live_checkout_mrr_usd"] != pair["intended_message_mrr_usd"]


def test_owner_metrics_keep_live_mrr_and_add_catalog_mrr(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.platform_owner_service import PlatformOwnerService

    root = tmp_path / "entitlements"
    root.mkdir()
    (root / "shop.json").write_text(
        '{"plan_id":"lite","status":"active","included_credits":7000}',
        encoding="utf-8",
    )
    monkeypatch.setattr("services.platform_owner_service._DATA_ROOT", tmp_path)
    metrics = PlatformOwnerService(root=tmp_path / "owner").business_metrics()
    assert metrics["mrr_usd"] == PLAN_PRICES_USD["lite"]
    assert metrics["intended_message_mrr_usd"] == 10.0


def test_expense_environment_stamps_prod(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "production")
    assert expense_environment() == "prod"
    record_expense(
        event_id="prod-1",
        tenant_id="shop",
        category="llm_generation",
        feature="customer_chat",
        provider="openai",
        model="answer",
        amount_usd=None,
        status="pending",
    )
    all_rows = global_dashboard()
    assert all_rows["pending_or_unpriced"] == 1
    assert "accepted" in all_rows["outbox"]
    assert all_rows["environment"] is None
    test_only = global_dashboard(environment="test")
    assert test_only["pending_or_unpriced"] == 0
    prod_only = global_dashboard(environment="prod")
    assert prod_only["pending_or_unpriced"] == 1


def test_iap_config_exposes_intended_message_prices() -> None:
    from services.store_iap_service import iap_config_status

    status = iap_config_status()
    assert status["plans"]["lite"] == PLAN_PRICES_USD["lite"]
    assert status["intended_message_prices_usd"]["lite"] == 10.0
