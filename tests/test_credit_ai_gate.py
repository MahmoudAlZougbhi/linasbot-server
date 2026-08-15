"""Credit ledger remaining is the only AI generation wallet — 0 remaining blocks."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.credit_ai_gate import (
    ai_generation_blocked,
    remaining_credits,
    upgrade_plan_allowed,
)
from services.credit_ledger_service import CreditLedgerService
from services.entitlements_service import EntitlementsStore
from services.membership.plan_catalog import is_highest_catalog_plan


@pytest.fixture()
def ledger_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> CreditLedgerService:
    store = EntitlementsStore(root=tmp_path / "ents")
    monkeypatch.setattr("services.entitlements_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_service.entitlements_store", store)
    monkeypatch.setattr("services.credit_ledger_pg_ops.entitlements_store", store)
    store.set_plan(tenant_id="clinic", plan_id="starter", status="active", source="admin")
    store.set_plan(tenant_id="linas", plan_id="max", status="active", source="admin")
    ledger = CreditLedgerService(root=tmp_path / "ledger")
    monkeypatch.setattr("services.credit_ledger_service.credit_ledger_service", ledger)
    return ledger


def _drain(ledger: CreditLedgerService, tenant_id: str, request_id: str) -> None:
    ledger.ensure_period_grant(tenant_id)
    available = ledger.get_balance(tenant_id)
    rid = ledger.reserve(
        tenant_id=tenant_id,
        user_id=None,
        credits=available,
        operation_type="test_drain",
        request_id=request_id,
    )
    ledger.capture(tenant_id=tenant_id, reservation_id=rid, provider_cost_usd=None, model_provider="test")


def test_zero_remaining_blocks_clinic(ledger_env: CreditLedgerService) -> None:
    _drain(ledger_env, "clinic", "drain-clinic")
    assert remaining_credits("clinic") == 0
    assert ai_generation_blocked("clinic") is True
    assert ai_generation_blocked("linas") is False
    assert ai_generation_blocked("") is True
    assert ai_generation_blocked(None) is True


def test_founder_linas_also_blocks_at_zero(ledger_env: CreditLedgerService) -> None:
    _drain(ledger_env, "linas", "drain-linas")
    assert remaining_credits("linas") == 0
    assert ai_generation_blocked("linas") is True


def test_upgrade_hidden_only_on_max() -> None:
    assert is_highest_catalog_plan("max") is True
    assert is_highest_catalog_plan("pro") is False
    assert is_highest_catalog_plan("linas") is False
    assert upgrade_plan_allowed("max") is False
    assert upgrade_plan_allowed("pro") is True
    assert upgrade_plan_allowed("starter") is True


def test_clinic_tenants_are_not_linas_exempt(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.entitlements_service import is_subscription_exempt_tenant
    from services.token_wallet_service import is_unlimited_tenant

    monkeypatch.delenv("SUBSCRIPTION_EXEMPT_TENANT_IDS", raising=False)
    monkeypatch.delenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", raising=False)
    assert is_subscription_exempt_tenant("linas") is True
    assert is_unlimited_tenant("linas") is True
    for tid in ("ok-clinic", "clinic", "linas-clinic", "linas_clinic"):
        assert is_subscription_exempt_tenant(tid) is False
        assert is_unlimited_tenant(tid) is False


@pytest.mark.asyncio
async def test_channel_orchestrator_does_not_generate_at_zero(
    ledger_env: CreditLedgerService, monkeypatch: pytest.MonkeyPatch
) -> None:
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    _drain(ledger_env, "clinic", "drain-orch")

    async def _must_not_faq(**_kwargs):  # noqa: ANN001
        raise AssertionError("FAQ must not reply at 0 credits")

    async def _must_not_answer(**_kwargs):  # noqa: ANN001
        raise AssertionError("Answer Luna must not run at 0 credits")

    monkeypatch.setattr("services.customer_reply_v2.faq_fast_path.try_faq_fast_path", _must_not_faq)
    monkeypatch.setattr("services.customer_reply_v2.orchestrator.run_answer_luna", _must_not_answer)

    out = await run_customer_reply_v2_dm(
        tenant_id="clinic",
        message="hi",
        detected_language="en",
        response_language="en",
    )
    assert out.reason == "insufficient_credits"
    assert out.reply is None
    assert out.metadata.get("ai_called") is False


@pytest.mark.asyncio
async def test_comment_orchestrator_does_not_generate_at_zero(ledger_env: CreditLedgerService) -> None:
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    _drain(ledger_env, "clinic", "drain-cmt")
    out = await run_customer_reply_v2_comment(
        tenant_id="clinic",
        comment_text="Nice!",
        comments_enabled=True,
    )
    assert out.reason == "insufficient_credits"
    assert out.reply is None


def test_try_reserve_fail_closed_at_zero(ledger_env: CreditLedgerService) -> None:
    from services.ai_reply_turn_runtime import try_reserve_for_ai

    _drain(ledger_env, "clinic", "drain-reserve")
    user_data = {"tenant_id": "clinic", "_source_message_id": "mid-1", "channel": "instagram"}
    assert try_reserve_for_ai(user_data) is False
    assert user_data.get("_ai_credit_blocked") is True
    missing = {"channel": "instagram", "_source_message_id": "mid-2"}
    assert try_reserve_for_ai(missing) is False


def test_copilot_pause_payload_hides_upgrade_on_max(ledger_env: CreditLedgerService) -> None:
    from services.credit_ai_gate import owner_credits_paused_payload

    _drain(ledger_env, "linas", "drain-max-payload")
    paused = owner_credits_paused_payload("linas")
    assert paused["show_upgrade"] is False
    assert paused["actions"]["upgrade_plan"] is False
    assert paused["actions"]["buy_credits"] is True
    clinic = owner_credits_paused_payload("clinic")
    assert clinic["show_upgrade"] is True
