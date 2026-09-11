"""Message catalog, ledger, daily edits, and cost dashboard — cutover still off."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal

import pytest

from services.membership.catalog_admin import CatalogPublishBlocked, publish, reset_catalog_admin_for_tests
from services.membership.cost_dashboard import global_dashboard, tenant_dashboard
from services.membership.daily_edits import (
    DailyEditLimitError,
    commit_edit,
    reserve_edit,
    reset_daily_edits_for_tests,
    set_tenant_override,
    status,
)
from services.membership.expense_journal import known_total, list_events, record_expense, reset_expenses_for_tests
from services.membership.lot_window import current_period_id
from services.membership.message_catalog import (
    PAID_PLANS,
    UNCONFIGURED_FREE_FIELDS,
    free_publish_blocked,
    message_catalog_snapshot,
    require_message_plan,
)
from services.membership.message_flags import message_billing_cutover, message_billing_enabled
from services.membership.message_ledger import (
    InsufficientMessages,
    grant_lot,
    grant_purchased,
    remaining_messages,
    reserve,
    reset_ledger_for_tests,
    settle,
)
from services.membership.message_policy import classify_turn, message_units_for


@pytest.fixture(autouse=True)
def _clean_stores(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_ledger_for_tests()
    reset_daily_edits_for_tests()
    reset_expenses_for_tests()
    reset_catalog_admin_for_tests()


def test_generative_gate_uses_messages_only_when_billing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.membership.generative_gate import generative_block_reason

    monkeypatch.setattr("services.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: True)
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "false")
    assert generative_block_reason("shop") == "insufficient_credits"
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    grant_lot(tenant_id="shop", lot_id="inc", kind="included", period_id=current_period_id(), amount=1)
    assert generative_block_reason("shop") is None


def test_flags_default_off() -> None:
    assert message_billing_enabled() is False
    assert message_billing_cutover() is False


def test_paid_matrix_matches_owner_contract() -> None:
    expected = {
        "lite": (10, 550, 50, 0, False),
        "starter": (29, 1200, 110, 2, True),
        "growth": (59, 3000, 250, 5, True),
        "pro": (120, 10000, 600, None, True),
        "max": (279, 25000, 1500, None, True),
    }
    for plan_id, (usd, messages, faq, seats, comments) in expected.items():
        plan = PAID_PLANS[plan_id]
        assert plan.price_micro_usd == usd * 1_000_000
        assert plan.included_messages == messages
        assert plan.faq_capacity == faq
        assert plan.additional_seats is seats
        assert plan.comment_automation is comments
        assert plan.faq_enabled is True
        assert plan.followup_enabled is True


def test_free_is_unpublishable() -> None:
    free = require_message_plan("free")
    assert free.included_messages is None
    assert free.faq_enabled is False
    assert free.followup_enabled is False
    assert free.public_sale is False
    assert free_publish_blocked() is True
    snap = message_catalog_snapshot()
    assert snap["free"]["publishable"] is False
    assert snap["free"]["unconfigured_fields"] == list(UNCONFIGURED_FREE_FIELDS)
    with pytest.raises(CatalogPublishBlocked):
        publish(actor="test")


def test_message_policy_zero_and_one() -> None:
    assert message_units_for("faq_only") == 0
    assert message_units_for("static") == 0
    assert message_units_for("generated_ai") == 1
    assert message_units_for("mixed_faq_ai") == 1
    assert message_units_for("followup_sent") == 1
    assert classify_turn(generated=False, faq_used=True) == "faq_only"
    assert classify_turn(generated=True, faq_used=True) == "mixed_faq_ai"


def test_ledger_faq_does_not_debit() -> None:
    grant_lot(tenant_id="t1", lot_id="inc-1", kind="included", period_id=current_period_id(), amount=550)
    reservation = reserve(tenant_id="t1", operation_id="faq-1", response_class="faq_only")
    settle(tenant_id="t1", operation_id="faq-1", accepted=True)
    assert reservation.units == 0
    assert remaining_messages("t1") == 550


def test_ledger_last_unit_race() -> None:
    grant_lot(tenant_id="t1", lot_id="inc-1", kind="included", period_id=current_period_id(), amount=1)

    def attempt(idx: int) -> str:
        try:
            reserve(tenant_id="t1", operation_id=f"op-{idx}", response_class="generated_ai")
            return "ok"
        except InsufficientMessages:
            return "blocked"

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(attempt, range(20)))
    assert results.count("ok") == 1
    assert results.count("blocked") == 19


def test_ledger_idempotent_operation() -> None:
    grant_lot(tenant_id="t1", lot_id="inc-1", kind="included", period_id=current_period_id(), amount=2)
    first = reserve(tenant_id="t1", operation_id="same", response_class="generated_ai")
    second = reserve(tenant_id="t1", operation_id="same", response_class="generated_ai")
    assert first.reservation_id == second.reservation_id
    settle(tenant_id="t1", operation_id="same", accepted=True)
    settle(tenant_id="t1", operation_id="same", accepted=True)
    assert remaining_messages("t1") == 1


def test_daily_edits_thirty_then_block() -> None:
    for idx in range(30):
        op = f"edit-{idx}"
        reserve_edit(tenant_id="shop", operation_id=op)
        commit_edit(tenant_id="shop", operation_id=op)
    with pytest.raises(DailyEditLimitError) as exc:
        reserve_edit(tenant_id="shop", operation_id="edit-30")
    assert exc.value.code == "AI_SETUP_DAILY_LIMIT"
    assert exc.value.decision.remaining == 0
    assert status("shop").used == 30


def test_daily_edit_raise_limit_does_not_reset_used() -> None:
    for idx in range(30):
        reserve_edit(tenant_id="shop", operation_id=f"e-{idx}")
        commit_edit(tenant_id="shop", operation_id=f"e-{idx}")
    set_tenant_override("shop", 50)
    decision = status("shop")
    assert decision.used == 30
    assert decision.remaining == 20
    assert decision.source == "tenant_override"


def test_expense_dashboard_reconciles_fixture_cents() -> None:
    record_expense(
        event_id="a",
        tenant_id="t1",
        category="llm_generation",
        feature="customer_chat",
        provider="openai",
        model="gpt-test",
        amount_usd="0.01",
    )
    record_expense(
        event_id="b",
        tenant_id="t1",
        category="translation",
        feature="faq",
        provider="openai",
        model="gpt-test",
        amount_usd="0.02",
    )
    record_expense(
        event_id="c",
        tenant_id="t1",
        category="embedding",
        feature="knowledge",
        provider="voyage",
        model="voyage-4-large",
        amount_usd="0.003",
    )
    events = list_events(tenant_id="t1")
    assert known_total(events) == Decimal("0.033")
    global_view = global_dashboard()
    tenant_view = tenant_dashboard("t1")
    assert global_view["known_usd"] == "0.033"
    assert global_view["reconciles"] is True
    assert tenant_view["known_usd"] == "0.033"
    assert Decimal(global_view["by_category"]["llm_generation"]) + Decimal(
        global_view["by_category"]["translation"]
    ) + Decimal(global_view["by_category"]["embedding"]) == Decimal("0.033")


def test_landing_and_app_removed_ai_limits_surfaces() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    how = (root / "dashboard" / "src" / "constants" / "landingHowItWorks.js").read_text(encoding="utf-8")
    control = (root / "dashboard" / "src" / "components" / "landing" / "sections" / "LandingControl.jsx").read_text(
        encoding="utf-8"
    )
    features = (root / "dashboard" / "src" / "pages" / "public" / "Features.jsx").read_text(encoding="utf-8")
    settings = (root / "mobile" / "linas-ai" / "src" / "features" / "settings" / "SettingsScreen.tsx").read_text(
        encoding="utf-8"
    )
    assert "AI Limits" not in how
    assert "CUSTOMER AI LIMITS" not in how
    assert "Protect your credits" not in how
    assert "id: 'limits'" not in control
    assert "Usage credits" not in features
    assert "onOpenAiLimits" not in settings
    assert "settingsAiLimits" not in settings


def test_public_plans_expose_messages_without_cutover() -> None:
    from modules.plans_api import public_plans

    body = asyncio.run(public_plans())
    assert body["consumption_unit"] == "messages"
    assert body["topup_unit"] == "credits"
    assert body["checkout_ready"] is False
    assert body["topup_packs"]
    assert all(pack.get("unit") == "credits" and pack.get("sale_ready") is False for pack in body["topup_packs"])
    assert "purchased_messages" not in body["topup_packs"][0]
    assert body["billing_period"] == "monthly"
    lite = next(plan for plan in body["plans"] if plan["plan_id"] == "lite")
    assert lite["included_messages"] == 550
    assert lite["intended_price_usd"] == 10
    assert lite["price_usd"] == 10
    assert lite["included_credits"] == 7000
    assert lite["live_store_price_usd"] == 9.99
    assert "credit_unit" not in body


def test_public_plans_omit_message_topups_until_sale_ready(monkeypatch: pytest.MonkeyPatch) -> None:
    from modules.plans_api import public_plans

    monkeypatch.setenv("MESSAGE_BILLING_CUTOVER", "true")
    body = asyncio.run(public_plans())
    assert body["consumption_unit"] == "messages"
    assert body["topup_unit"] == "credits"
    assert body["topup_packs"] == []
    assert body["checkout_ready"] is True


def test_message_gate_only_when_flag_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.contracts.turn import CustomerTurn
    from services.customer_ai.gates import evaluate_gates

    turn = CustomerTurn(tenant_id="t-gate", customer_id="c1", conversation_id="conv")
    monkeypatch.setattr("services.customer_ai.gates.live_handoff_active", lambda **_k: False)
    monkeypatch.setattr("services.customer_ai.gates.read_published_pointer", lambda *_a, **_k: object())
    monkeypatch.setattr("services.customer_ai.gates.find_published_restricted", lambda *_a, **_k: None)
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    decision = evaluate_gates(turn)
    assert decision.allow is False
    assert decision.reason == "insufficient_messages"
    grant_lot(tenant_id="t-gate", lot_id="inc", kind="included", period_id=current_period_id(), amount=1)
    assert evaluate_gates(turn).allow is True


def test_daily_edit_commit_is_idempotent() -> None:
    reserve_edit(tenant_id="shop", operation_id="same-edit")
    commit_edit(tenant_id="shop", operation_id="same-edit")
    commit_edit(tenant_id="shop", operation_id="same-edit")
    reserve_edit(tenant_id="shop", operation_id="same-edit")
    assert status("shop").used == 1


def test_failed_generate_releases_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai.billing import apply_message_billing, reserve_generative
    from services.customer_ai.contracts.reply import FinalReplyEnvelope, TurnResult
    from services.customer_ai.contracts.turn import CustomerTurn
    from services.membership.pending_settlement import get_pending, reset_pending_settlements_for_tests

    reset_pending_settlements_for_tests()
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    grant_lot(tenant_id="t-bill", lot_id="inc", kind="included", period_id=current_period_id(), amount=2)
    turn = CustomerTurn(tenant_id="t-bill", conversation_id="c1", event_ids=["evt-1"])
    assert reserve_generative(turn) is None
    assert remaining_messages("t-bill") == 1
    held = get_pending("t-bill", "evt-1", "evt-1")
    assert held is not None
    assert "c1" in (held.extra.get("candidate_ids") or [])
    result = apply_message_billing(
        turn,
        TurnResult(stop_reason="failed_closed", envelope=FinalReplyEnvelope(decision="no_reply")),
    )
    assert result.stop_reason == "failed_closed"
    assert remaining_messages("t-bill") == 2
    released = get_pending("t-bill", "evt-1", "evt-1")
    assert released is not None
    assert released.state == "released"


def test_message_surface_hides_credit_quantities(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.tenant_mobile_dashboard.message_surface import (
        overlay_message_fields,
        workspace_message_balance,
    )

    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "false")
    fields = overlay_message_fields("t1", "lite")
    assert fields["message_billing_active"] is False
    assert fields["wallet_unit"] == "credits"
    assert "not Messages remaining" in fields["speak_as"]
    assert fields["included_messages"] == 550
    assert fields["available_messages"] is None
    assert fields["usage_progress_ratio"] is None
    remaining, included, known = workspace_message_balance(
        {"availability": "ok", "available_credits": 7000, "included_credits": 7000}
    )
    assert remaining is None
    assert included == 0
    assert known is False
    depleted, _, depleted_known = workspace_message_balance(
        {"availability": "ok", "available_credits": 0, "included_credits": 7000}
    )
    assert depleted is None
    assert depleted_known is False
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    grant_lot(tenant_id="surf-lite", lot_id="lite-now", kind="included", period_id=current_period_id(), amount=400)
    live = overlay_message_fields("surf-lite", "lite")
    assert live["message_billing_active"] is True
    assert live["included_messages"] == 550
    assert live["included_remaining"] == 400
    assert live["available_messages"] == 400
    assert live["granted_messages"] == 400
    assert live["used_messages"] == 0


def test_cost_dashboard_filters_and_message_totals() -> None:
    grant_lot(tenant_id="shop-a", lot_id="inc-a", kind="included", period_id=current_period_id(), amount=10)
    reserve(tenant_id="shop-a", operation_id="gen-1", response_class="generated_ai")
    settle(tenant_id="shop-a", operation_id="gen-1", accepted=True)
    record_expense(
        event_id="llm-1",
        tenant_id="shop-a",
        category="llm_generation",
        feature="customer_chat",
        provider="openai",
        model="answer",
        amount_usd="0.02",
        status="known",
    )
    record_expense(
        event_id="tr-1",
        tenant_id="shop-a",
        category="translation",
        feature="faq",
        provider="openai",
        model="translate",
        amount_usd="0.01",
        status="known",
    )
    dash = tenant_dashboard("shop-a", category="translation")
    assert dash["by_category"] == {"translation": "0.01"}
    assert "llm_generation" not in dash["by_category"]
    assert dash["messages"]["allocated"] == 10
    assert dash["messages"]["used"] == 1
    assert dash["messages"]["remaining"] == 9
    assert dash["messages"]["message_billing_active"] is False
    glob = global_dashboard()
    assert glob["messages"]["message_billing_active"] is False
    assert glob["by_feature"]["faq"] == "0.01"
    assert glob["by_feature"]["customer_chat"] == "0.02"
    assert glob["by_provider"]["openai"] == "0.03"
    assert glob["by_model"]["answer"] == "0.02"
    assert glob["daily_edits"]["used"] >= 0
    assert "shop-a" in {row["tenant_id"] for row in glob["daily_edits"]["tenants"]}


def test_purchased_lot_used_after_included() -> None:
    grant_lot(tenant_id="mix", lot_id="inc", kind="included", period_id=current_period_id(), amount=1)
    grant_purchased(tenant_id="mix", lot_id="pack", amount=3, source_transaction_id="txn-1")
    reserve(tenant_id="mix", operation_id="a", response_class="generated_ai")
    settle(tenant_id="mix", operation_id="a", accepted=True)
    reserve(tenant_id="mix", operation_id="b", response_class="generated_ai")
    settle(tenant_id="mix", operation_id="b", accepted=True)
    snap = remaining_messages("mix")
    assert snap == 2


def test_followup_locked_on_free_and_none() -> None:
    from services.membership.feature_entitlements import faq_limits_for_plan, followup_allowed_for_plan

    assert followup_allowed_for_plan("free") is False
    assert followup_allowed_for_plan("lite") is True
    assert faq_limits_for_plan("lite") == (True, 50)
    assert faq_limits_for_plan("free") == (False, 0)


def test_followup_assert_waits_for_enforcement_flag(monkeypatch) -> None:
    from services.entitlements_service import entitlements_store
    from services.membership.feature_entitlements import FeatureDenied, assert_followup_allowed

    entitlements_store.set_plan(tenant_id="free-tenant", plan_id="free", status="active", source="admin")
    monkeypatch.delenv("MESSAGE_BILLING_ENABLED", raising=False)
    monkeypatch.delenv("FREE_PLAN_ENFORCEMENT_ENABLED", raising=False)
    assert_followup_allowed("free-tenant")

    monkeypatch.setenv("FREE_PLAN_ENFORCEMENT_ENABLED", "true")
    try:
        assert_followup_allowed("free-tenant")
        raise AssertionError("expected FeatureDenied")
    except FeatureDenied as exc:
        assert exc.code == "FOLLOWUP_DISABLED"


def test_payment_readiness_blocks_google_and_annual() -> None:
    from services.membership.catalog_admin import current_catalog

    ready = current_catalog()["payment_readiness"]
    assert ready["google"]["sale_ready"] is False
    assert ready["annual_offers"]["sale_ready"] is False
    assert ready["stripe"]["blocker"] == "not_message_subscription_checkout"
    assert ready["cutover"] is False


def test_cost_period_bounds_today() -> None:
    from services.membership.cost_dashboard import period_bounds

    start, end = period_bounds("today")
    assert start and end
    assert start[:10] == end[:10]


def test_set_plan_grants_included_when_billing_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.entitlements_service import entitlements_store

    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    entitlements_store.set_plan(tenant_id="grant-tenant", plan_id="lite", status="active", source="admin")
    assert remaining_messages("grant-tenant") == 550


def test_conversion_dry_run_lists_credits_but_stays_blocked() -> None:
    from services.entitlements_service import entitlements_store
    from services.membership.conversion_dry_run import dry_run_credit_inventory

    entitlements_store.set_plan(tenant_id="inv-tenant", plan_id="lite", status="active", source="admin")
    result = dry_run_credit_inventory(["inv-tenant"])
    assert result["blocked"] is True
    assert result["assumed_rate"] is None
    assert result["tenants"][0]["converted"] is False
    assert result["tenants"][0]["proposed_messages"] is None
    assert result["tenants"][0]["included_credits"] >= 0


def test_stale_included_lot_does_not_spend() -> None:
    from services.membership.reconcile import ledger_health

    grant_lot(tenant_id="stale", lot_id="old", kind="included", period_id="2025-01", amount=50)
    grant_purchased(tenant_id="stale", lot_id="pack", amount=2, source_transaction_id="txn-stale")
    assert remaining_messages("stale") == 2
    reserve(tenant_id="stale", operation_id="use-1", response_class="generated_ai")
    settle(tenant_id="stale", operation_id="use-1", accepted=True)
    assert remaining_messages("stale") == 1
    health = ledger_health("stale")
    assert health["ok"] is True
    assert health["store"] == "memory"
    assert "old" in health["stale_included"]
