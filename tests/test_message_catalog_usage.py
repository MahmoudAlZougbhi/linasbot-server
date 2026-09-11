"""Catalog SoT overlays, usage-class costs, IAP grant hook, force-reindex."""

from __future__ import annotations

import asyncio

import pytest

from services.membership.catalog_admin import (
    CatalogPublishBlocked,
    current_catalog,
    effective_offer_fields,
    publish,
    reset_catalog_admin_for_tests,
    update_draft,
)
from services.membership.cost_dashboard import global_dashboard, tenant_dashboard
from services.membership.iap_message_grant import (
    grant_from_mapped_pack,
    maybe_grant_purchased_from_verified_txn,
)
from services.membership.lot_window import current_period_id
from services.membership.message_catalog import offer_fields_for_plan
from services.membership.message_flags import message_billing_cutover
from services.membership.message_ledger import grant_lot, remaining_messages, reserve, reset_ledger_for_tests, settle


@pytest.fixture(autouse=True)
def _clean(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_ledger_for_tests()
    reset_catalog_admin_for_tests()


def test_offer_fields_include_message_catalog_faq() -> None:
    fields = offer_fields_for_plan("lite")
    assert fields["faq_capacity"] == 50
    assert fields["included_messages"] == 550
    assert effective_offer_fields("pro")["faq_capacity"] == 600


def test_public_plans_faq_capacity_from_message_catalog() -> None:
    from modules.plans_api import public_plans

    body = asyncio.run(public_plans())
    lite = next(plan for plan in body["plans"] if plan["plan_id"] == "lite")
    assert lite["faq_capacity"] == 50
    assert lite["included_messages"] == 550
    assert lite["intended_price_usd"] == 10
    assert lite["comment_automation"] is False
    assert lite["whatsapp"] is False
    assert lite["web"] is False
    assert lite["tiktok"] is False
    assert lite["features"]["web"] is False
    starter = next(plan for plan in body["plans"] if plan["plan_id"] == "starter")
    assert starter["comment_automation"] is True
    assert starter["whatsapp"] is True
    assert starter["web"] is True
    assert starter["tiktok"] is False
    assert starter["additional_seats"] == 2
    assert lite["additional_seats"] == 0


def test_paid_plan_draft_does_not_change_public_until_publish() -> None:
    catalog = update_draft(
        actor="owner",
        changes={"plans": {"lite": {"intended_price_usd": 11, "included_messages": 600, "faq_capacity": 60}}},
        reason="preview",
    )
    lite = next(plan for plan in catalog["plans"] if plan["plan_id"] == "lite")
    assert lite["included_messages"] == 600
    assert lite["faq_capacity"] == 60
    assert lite["draft_overlay"] is True
    assert lite["checkout_ready"] is False
    from modules.plans_api import public_plans

    public = asyncio.run(public_plans())
    public_lite = next(plan for plan in public["plans"] if plan["plan_id"] == "lite")
    assert public_lite["included_messages"] == 550
    assert public_lite["faq_capacity"] == 50
    assert public_lite["intended_price_usd"] == 10
    with pytest.raises(CatalogPublishBlocked):
        publish(actor="owner")
    assert current_catalog()["published"] is False
    assert effective_offer_fields("lite")["included_messages"] == 550


def test_draft_rejects_free_plan_overlay() -> None:
    with pytest.raises(ValueError, match="free"):
        update_draft(actor="owner", changes={"plans": {"free": {"included_messages": 20}}})


def test_catalog_admin_persists_outside_memory_store(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.delenv("LINAS_BILLING_BACKEND", raising=False)
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from services.membership import catalog_admin as admin

    admin.reset_catalog_admin_for_tests()
    update_draft(actor="owner", changes={"plans": {"lite": {"included_messages": 600}}}, reason="disk")
    path = tmp_path / "platform" / "message_catalog_admin.json"
    assert path.is_file()
    admin._DRAFT.clear()
    admin._REVISION = 1
    admin._LOADED = False
    restored = current_catalog()
    lite = next(plan for plan in restored["plans"] if plan["plan_id"] == "lite")
    assert lite["included_messages"] == 600
    assert restored["published"] is False


def test_comments_locked_on_lite_and_free() -> None:
    from services.membership.feature_entitlements import (
        channel_flags_for_plan,
        comments_allowed_for_plan,
        tiktok_allowed_for_plan,
        web_allowed_for_plan,
        whatsapp_allowed_for_plan,
    )

    assert comments_allowed_for_plan("lite") is False
    assert comments_allowed_for_plan("starter") is True
    assert comments_allowed_for_plan("free") is False
    assert whatsapp_allowed_for_plan("lite") is False
    assert whatsapp_allowed_for_plan("starter") is True
    assert web_allowed_for_plan("lite") is False
    assert tiktok_allowed_for_plan("lite") is False
    assert tiktok_allowed_for_plan("growth") is True
    flags = channel_flags_for_plan("lite")
    assert flags["comment_automation"] is False
    assert flags["faq_enabled"] is True


def test_entitlements_me_overlays_message_channel_flags(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore, get_tenant_entitlement_public

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    store.set_plan(tenant_id="lite-ent", plan_id="lite", status="active", source="admin")
    pub = get_tenant_entitlement_public("lite-ent")
    assert pub["comment_automation"] is False
    assert pub["whatsapp"] is False
    assert pub["web"] is False
    assert pub["tiktok"] is False
    assert pub["features"]["faq_enabled"] is True
    assert pub["price_usd"] == 9.99
    assert pub["additional_seats"] == 0
    assert pub["message_billing_active"] is False
    assert pub["included_messages"] == 550
    assert pub["available_messages"] is None
    store.set_plan(tenant_id="grow-ent", plan_id="growth", status="active", source="admin")
    grow = get_tenant_entitlement_public("grow-ent")
    assert grow["comment_automation"] is True
    assert grow["whatsapp"] is True
    assert grow["tiktok"] is True
    assert grow["price_usd"] == 59.0


def test_ledger_health_reports_memory_store() -> None:
    from services.membership.reconcile import ledger_health

    health = ledger_health("store-check")
    assert health["store"] == "memory"


def test_usage_classes_split_faq_and_generative() -> None:
    grant_lot(tenant_id="usage-shop", lot_id="inc", kind="included", period_id=current_period_id(), amount=10)
    reserve(tenant_id="usage-shop", operation_id="gen-1", response_class="generated_ai")
    settle(tenant_id="usage-shop", operation_id="gen-1", accepted=True)
    reserve(tenant_id="usage-shop", operation_id="faq-1", response_class="faq_only")
    settle(tenant_id="usage-shop", operation_id="faq-1", accepted=True)
    reserve(tenant_id="usage-shop", operation_id="static-1", response_class="static")
    settle(tenant_id="usage-shop", operation_id="static-1", accepted=True)
    dash = tenant_dashboard("usage-shop")
    assert dash["usage_classes"]["generative"]["settled_units"] == 1
    assert dash["usage_classes"]["faq_or_static"]["count"] == 2
    assert dash["usage_classes"]["faq_or_static"]["settled_units"] == 0
    assert dash["messages"]["used"] == 1
    assert "pending_settlements" in dash
    assert "leftover_credit_holds" in dash
    assert "processing_budgets" in dash
    glob = global_dashboard()
    assert glob["usage_classes"]["generative"]["settled_units"] >= 1
    assert glob["usage_classes"]["faq_or_static"]["count"] >= 2
    assert glob["messages"]["used"] >= 1
    assert glob["messages"]["reserved"] >= 0
    assert "pending_settlements" in glob
    assert "leftover_credit_holds" in glob
    assert "processing_budgets" in glob


def test_cost_dashboard_filters_by_model() -> None:
    from services.membership.expense_journal import record_expense, reset_expenses_for_tests

    reset_expenses_for_tests()
    record_expense(
        event_id="model-filter-1",
        tenant_id="usage-shop",
        category="llm_generation",
        feature="planning",
        provider="openai",
        model="planner-test",
        amount_usd="0.01",
        status="known",
    )
    record_expense(
        event_id="model-filter-2",
        tenant_id="usage-shop",
        category="llm_generation",
        feature="customer_chat",
        provider="openai",
        model="answer-test",
        amount_usd="0.02",
        status="known",
    )
    filtered = global_dashboard(model="planner-test")
    assert filtered["filters"]["model"] == "planner-test"
    assert filtered["by_model"] == {"planner-test": "0.01"}
    assert filtered["by_feature"].get("planning") == "0.01"


def test_iap_grant_stays_off_without_cutover_or_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    assert message_billing_cutover() is False
    skipped = maybe_grant_purchased_from_verified_txn(
        tenant_id="iap-shop",
        product_id="com.linasai.credits.2500",
        transaction_id="txn-credit",
    )
    assert skipped == {"granted": False, "reason": "cutover_off"}
    monkeypatch.setenv("MESSAGE_BILLING_CUTOVER", "true")
    unmapped = maybe_grant_purchased_from_verified_txn(
        tenant_id="iap-shop",
        product_id="com.linasai.credits.2500",
        transaction_id="txn-credit",
    )
    assert unmapped == {"granted": False, "reason": "unmapped_or_unpriced_pack"}
    assert remaining_messages("iap-shop") == 0


def test_iap_grant_from_explicit_sale_ready_pack() -> None:
    result = grant_from_mapped_pack(
        tenant_id="pack-shop",
        transaction_id="txn-pack-1",
        pack={"pack_id": "messages_100", "quantity": 100, "price_usd": 4, "sale_ready": True},
    )
    assert result["granted"] is True
    assert result["amount"] == 100
    assert remaining_messages("pack-shop") == 100
    again = grant_from_mapped_pack(
        tenant_id="pack-shop",
        transaction_id="txn-pack-1",
        pack={"pack_id": "messages_100", "quantity": 100, "price_usd": 4, "sale_ready": True},
    )
    assert again["granted"] is True
    assert remaining_messages("pack-shop") == 100


def test_force_reindex_unpublished() -> None:
    from services.customer_ai.search.force_reindex import force_reindex_tenant

    result = asyncio.run(force_reindex_tenant("no-pointer-tenant"))
    assert result["ready"] is False
    assert result["reason"] == "unpublished"


def test_force_reindex_uses_processing_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.cm.schemas import PublishedPointer
    from services.customer_ai.search.force_reindex import force_reindex_tenant
    from services.membership.processing_budgets import begin_job, reset_processing_budgets_for_tests

    reset_processing_budgets_for_tests()
    begin_job("busy-tenant")
    begin_job("busy-tenant")
    monkeypatch.setattr(
        "services.customer_ai.search.force_reindex.read_published_pointer",
        lambda _tid: PublishedPointer(
            content_version_id="v1",
            index_version_id="i1",
            checksums={},
            embedding_provider="voyage",
            embedding_model="test",
            embedding_version="1",
            embedding_dimensions=4,
        ),
    )
    result = asyncio.run(force_reindex_tenant("busy-tenant"))
    assert result["ready"] is False
    assert result["reason"] == "PROCESSING_CONCURRENCY"


def test_google_notification_attaches_cutover_off_grant(monkeypatch: pytest.MonkeyPatch) -> None:
    from modules.store_iap_api import apply_google_notification_effect

    monkeypatch.setattr(
        "modules.store_iap_api.apply_normalized_notification",
        lambda **_k: {"applied": True, "plan_id": "starter"},
    )
    result = apply_google_notification_effect(
        {
            "tenant_id": "g-shop",
            "product_id": "linas_ai_starter_monthly",
            "subscription_state": "ACTIVE",
            "original_transaction_id": "txn-g",
            "event_id": "evt-g",
        }
    )
    assert result["applied"] is True
    assert result["message_grant"] == {"granted": False, "reason": "cutover_off"}


def test_google_unmapped_sku_grants_only_sale_ready_pack(monkeypatch: pytest.MonkeyPatch) -> None:
    from modules.store_iap_api import apply_google_notification_effect

    monkeypatch.setattr(
        "modules.store_iap_api.apply_normalized_notification",
        lambda **_k: (_ for _ in ()).throw(ValueError("Unmapped store product")),
    )
    monkeypatch.setenv("MESSAGE_BILLING_CUTOVER", "true")
    with pytest.raises(ValueError):
        apply_google_notification_effect(
            {
                "tenant_id": "g-pack",
                "product_id": "com.linasai.messages.100",
                "subscription_state": "ACTIVE",
                "original_transaction_id": "txn-pack",
                "event_id": "evt-pack",
            }
        )
    granted = grant_from_mapped_pack(
        tenant_id="g-pack",
        transaction_id="txn-pack",
        pack={"pack_id": "messages_100", "quantity": 100, "price_usd": 4, "sale_ready": True},
    )
    assert granted["granted"] is True


def test_offline_eval_contract_cases() -> None:
    from services.customer_ai.evals.runner import run_fixture_corpus

    result = run_fixture_corpus()
    assert result["live_spend"] is False
    assert result["ok"] is True
    assert result["case_count"] >= 15
    ids = {item["id"] for item in result["contract_cases"]}
    assert "faq_exact_zero" in ids
    assert "lite_comments_locked" in ids
    assert "free_faq_locked" in ids
    assert "activation_flags_off" in ids
    assert "comment_no_greeting" in ids
    assert "followup_no_greeting" in ids
    assert "comment_static_zero" in ids
    assert "comment_ai_bundle_one" in ids
    assert "planner_negates_booking" in ids
    assert "planner_correction" in ids
    assert "generate_persists_without_capture" in ids
    assert "stale_leftover_not_refunded" in ids
    assert "tiktok_media_reaches_brain" in ids
    assert "meta_ai_dm_reaches_brain" in ids
    assert "history_routes_by_channel" in ids
    assert "web_chat_indexes_leftover" in ids
    assert "legacy_photo_fetches_ssrf_safe" in ids
    assert "index_seeds_from_pending" in ids
    assert "meta_ai_both_skips_public_after_reply" in ids
    assert "tiktok_comment_settles_after_send" in ids
    assert "legacy_voice_journals_stt" in ids
    assert "meta_public_comment_settles" in ids


@pytest.mark.asyncio
async def test_copilot_read_usage_keeps_credits_off_message_remaining(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore
    from services.owner_ai_tools_read import tool_read_usage

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    store.set_plan(tenant_id="lite-usage", plan_id="lite", status="active", source="admin")
    result = await tool_read_usage(tenant_id="lite-usage", role="admin")
    assert result.ok is True
    assert result.data["wallet_unit"] == "credits"
    assert result.data["message_billing_active"] is False
    assert result.data["included_messages"] == 550
    assert result.data["available_messages"] is None
    assert "leftover credits" in result.data["speak_as"]


def test_cost_dashboard_grants_included_when_billing_on(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services import entitlements_service as es
    from services.entitlements_service import EntitlementsStore

    store = EntitlementsStore(root=tmp_path / "ent")
    monkeypatch.setattr(es, "entitlements_store", store)
    store.set_plan(tenant_id="lite-cost", plan_id="lite", status="active", source="admin")
    monkeypatch.setenv("MESSAGE_BILLING_ENABLED", "true")
    dash = tenant_dashboard("lite-cost")
    assert dash["messages"]["message_billing_active"] is True
    assert dash["messages"]["allocated"] == 550
    assert dash["messages"]["remaining"] == 550


def test_topup_pack_product_id_draft_stays_unpriced() -> None:
    catalog = update_draft(
        actor="owner",
        changes={"topup_packs": {"messages_100": {"product_id": "com.linasai.messages.100"}}},
        reason="map-sku",
    )
    pack = next(item for item in catalog["topup_packs"] if item["pack_id"] == "messages_100")
    assert pack["product_id"] == "com.linasai.messages.100"
    assert pack["sale_ready"] is False
    assert pack["price_usd"] is None


def test_free_draft_records_owner_values_without_inventing_the_rest() -> None:
    catalog = update_draft(
        actor="owner",
        changes={
            "free": {
                "included_messages": 0,
                "configured": {"free_message_renewal": "none"},
            }
        },
        reason="portal_edit",
    )
    free = catalog["free"]
    assert free["included_messages"] == 0
    assert "free_ai_message_allowance" not in free["unconfigured_fields"]
    assert "knowledge_line_budget" in free["unconfigured_fields"]
    assert "message_topup_prices" in free["unconfigured_fields"]
    assert "credit_to_message_conversion" in free["unconfigured_fields"]


def test_owner_portal_wires_catalog_costs_and_lab() -> None:
    from pathlib import Path

    root = Path("dashboard/src/pages/owner")
    catalog = (root / "OwnerCatalog.jsx").read_text(encoding="utf-8")
    costs = (root / "OwnerCosts.jsx").read_text(encoding="utf-8")
    lab = (root / "OwnerLab.jsx").read_text(encoding="utf-8")
    api = (root / "ownerApi.js").read_text(encoding="utf-8")
    assert "freeDraftFromCatalog" in catalog
    assert "leave empty until decided" in catalog
    assert "patchDailyEdits" in catalog
    assert "usage_classes?.by_class" in costs
    assert "daily_edits?.tenants" in costs
    assert "labClassify" in lab
    assert "Classify units" in lab
    assert "customer-ai-lab/classify" in api
    assert "/api/platform/daily-edits" in api
    banner = (root / "OwnerActivationBanner.jsx").read_text(encoding="utf-8")
    assert "durable_tables" in banner
    assert "Activation stays off" in banner


def test_cost_dashboard_includes_processing_and_edit_tenants() -> None:
    from services.customer_ai.contracts.turn import ConversationState
    from services.customer_ai.conversation_store import reset_conversation_store_for_tests, save_conversation
    from services.membership.daily_edits import commit_edit, reserve_edit, reset_daily_edits_for_tests
    from services.membership.processing_budgets import consume_attempt, reset_processing_budgets_for_tests

    reset_processing_budgets_for_tests()
    reset_daily_edits_for_tests()
    reset_conversation_store_for_tests()
    consume_attempt("proc-only")
    reserve_edit(tenant_id="edit-only", operation_id="op-edit")
    commit_edit(tenant_id="edit-only", operation_id="op-edit")
    save_conversation("conv-only", "web:conv-only:visitor", ConversationState(greeted=True), [])
    tenants = {row["tenant_id"] for row in global_dashboard()["daily_edits"]["tenants"]}
    assert "proc-only" in tenants
    assert "edit-only" in tenants
    assert "conv-only" in tenants
