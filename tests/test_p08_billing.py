"""P08 billing and Copilot fixes. New behavior stays off unless its flag is on."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from services.billing.membership.balances import membership_can_grant, split_charge, tenant_balances
from services.billing.membership.copilot_pricing import (
    estimate_copy,
    messages_for_tokens,
    validate_token_policy,
)
from services.billing.membership.message_ledger import grant_lot, grant_purchased, reset_ledger_for_tests
from services.billing.membership.pricing_store import active_policy, reset_pricing_for_tests, save_policy
from services.owner_copilot.cost_estimator import estimate_turn
from services.owner_copilot.estimates import EstimateError, approve, create_estimate, decline, reset_estimates_for_tests
from services.owner_copilot.section_counts import count_records
from services.owner_copilot.turn_jobs import append_event, replay, reset_turns_for_tests, run_with_deadline, settle_once
from services.owner_portal.qa_match import pick_variant
from services.owner_portal.translation_guard import cleanup_candidate, translation_is_clean


def _on(monkeypatch: pytest.MonkeyPatch, name: str) -> None:
    monkeypatch.setenv(f"LINAS_FLAG_{name.upper()}", "on")


@pytest.fixture(autouse=True)
def _clean() -> None:
    reset_pricing_for_tests()
    reset_estimates_for_tests()
    reset_ledger_for_tests()
    reset_turns_for_tests()


def test_token_bands_clamp_and_require_a_note() -> None:
    policy = active_policy()
    assert messages_for_tokens(1000, policy) == 1
    assert messages_for_tokens(31000, policy) == 3
    assert messages_for_tokens(90000, policy) == 8
    capped = {**policy, "max_messages_per_request": 10}
    assert messages_for_tokens(200000, capped) == 8
    wider = {
        **policy,
        "token_bands": policy["token_bands"][:-1] + [{"min_tokens": 80001, "max_tokens": None, "messages": 14}],
    }
    assert messages_for_tokens(200000, {**wider, "max_messages_per_request": 10}) == 10
    with pytest.raises(ValueError):
        validate_token_policy({"token_bands": [{"min_tokens": 5, "max_tokens": 10, "messages": 1}]})
    with pytest.raises(ValueError):
        save_policy(body=policy, created_by="owner", note="  ")
    save_policy(body=policy, created_by="owner", note="Raise the open band")
    assert active_policy()["policy_version"] == "message-economy-v2"


def test_big_audit_asks_for_approval_and_decline_is_free(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.message_billing import owner_turn_hold_begin

    _on(monkeypatch, "copilot_pricing_v2")

    def reserved(**kwargs):
        _ = kwargs
        raise AssertionError("nothing should be reserved")

    monkeypatch.setattr("services.owner_copilot.message_billing.reserve", reserved)
    hold = owner_turn_hold_begin("shop", user_text="review all my AI setup and fix everything", conversation_id="c1")
    assert hold.confirm_required is True
    assert hold.units > 1
    cheap = estimate_turn(user_text="how many branches do I have?")
    assert cheap["needs_approval"] is False
    assert cheap["messages_high"] == 1
    row = create_estimate(tenant_id="shop", user_id="owner", policy=active_policy())
    declined = decline(row["id"])
    assert declined["charged"] == 0
    assert declined["ledger_reason"] == "copilot_declined"


def test_approve_charges_actual_tokens_even_above_the_estimate() -> None:
    policy = active_policy()
    row = create_estimate(tenant_id="shop", user_id="owner", policy=policy, messages_low=4, messages_high=7)
    approved = approve(row["id"], actual_tokens=90000, tenant_id="shop", user_id="owner")
    assert approved["charged"] == messages_for_tokens(90000, policy)
    assert approved["charged"] == 8
    again = approve(row["id"], actual_tokens=1, tenant_id="shop", user_id="owner")
    assert again["charged"] == 8
    low = create_estimate(tenant_id="shop", user_id="owner", policy=policy)
    assert approve(low["id"], actual_tokens=25000, tenant_id="shop", user_id="owner")["charged"] == 3
    expired = create_estimate(tenant_id="shop", user_id="owner", policy=policy)
    expired["expires_at"] = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
    with pytest.raises(EstimateError) as exc:
        approve(expired["id"], actual_tokens=1000, tenant_id="shop", user_id="owner")
    assert exc.value.status == 410
    copy = estimate_copy(
        messages_low=4,
        messages_high=7,
        tokens_low=25000,
        tokens_high=45000,
        expected_tools=12,
        plan_remaining=24945,
        purchased_remaining=0,
    )
    assert "between 4 and 7 messages, or more" in copy["en"]
    assert "بين 4 و 7" in copy["ar"]
    assert "entre 4 et 7" in copy["fr"]


def test_plan_expires_and_purchased_remains(monkeypatch: pytest.MonkeyPatch) -> None:
    _on(monkeypatch, "period_balances")
    ended = SimpleNamespace(status="active", current_period_end=datetime(2026, 9, 14, tzinfo=UTC))
    assert membership_can_grant(ended, now=datetime(2026, 10, 9, tzinfo=UTC)) is False
    plan = SimpleNamespace(
        kind="included", granted=10, remaining=10, expires=True, expires_at=datetime(2026, 9, 14, tzinfo=UTC)
    )
    bought = SimpleNamespace(kind="purchased", granted=5, remaining=5, expires=False, expires_at=None)
    balances = tenant_balances([plan, bought])
    assert balances["plan"]["remaining"] == 0
    assert balances["purchased"]["remaining"] == 5
    assert balances["purchased"]["never_expires"] is True
    taken_plan, taken_bought = split_charge(plan_remaining=10, purchased_remaining=5, amount=12)
    assert (taken_plan, taken_bought) == (10, 2)
    used = tenant_balances(
        [
            SimpleNamespace(
                kind="included",
                granted=25000,
                remaining=24945,
                expires=True,
                expires_at=datetime(2099, 1, 1, tzinfo=UTC),
                period_id="2099-01",
            )
        ]
    )
    assert used["used_messages"] == 55


def test_purchased_balance_keeps_web_chat_open(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.billing.membership.web_gate import WebPlanDenied, assert_web_plan_allowed

    grant_purchased(tenant_id="shop", lot_id="pack", amount=10, source_transaction_id="txn-1")
    ent = SimpleNamespace(status="canceled", plan_id="growth")
    monkeypatch.setattr("services.billing.membership.web_gate.entitlements_store.get", lambda tenant_id: ent)
    with pytest.raises(WebPlanDenied):
        assert_web_plan_allowed("shop")
    _on(monkeypatch, "period_balances")
    assert_web_plan_allowed("shop")


def test_counts_language_and_qa_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.profile import resolve_owner_reply_language

    items = [{"status": "active"}] * 5 + [{"status": "archived"}] * 6
    assert count_records(items) == {"active": 5, "total": 11}
    assert resolve_owner_reply_language("shu howe", reply_language_override="en") == "ar"
    _on(monkeypatch, "copilot_reply_language")
    assert resolve_owner_reply_language("shu howe", reply_language_override="en") == "en"
    variants = [
        {"language": "fr", "answer": "french"},
        {"language": "franco", "answer": "franco"},
        {"language": "en", "answer": "english"},
    ]
    assert pick_variant(variants, "franco") == "franco"
    assert (
        pick_variant([{"language": "fr", "answer": "french"}, {"language": "en", "answer": "english"}], "franco")
        == "english"
    )


def test_instruction_lines_are_rejected() -> None:
    source = "The teal-marten refund code is 5172."
    leaked = source + "\nConservez chaque espace réservé exactement comme écrit."
    assert translation_is_clean(source, source) is True
    assert translation_is_clean(source, leaked) is False
    assert cleanup_candidate(leaked) is True


def test_turn_can_resume_and_the_lab_deadline_fires() -> None:
    append_event("turn-1", {"type": "delta", "text": "Hello"})
    assert settle_once("turn-1") is True
    assert settle_once("turn-1") is False
    assert replay("turn-1")[0]["text"] == "Hello"

    async def slow():
        await asyncio.sleep(2)
        return {"ok": True}

    result = asyncio.run(run_with_deadline(slow(), seconds=0.01))
    assert result["error"] == "timed_out"


def test_empty_send_is_not_charged_when_the_flag_is_on(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.brain.billing import settle_after_send

    grant_lot(tenant_id="shop", lot_id="lot", kind="included", period_id="forever", amount=5, expires=False)
    from services.billing.membership.message_ledger import reserve

    reserve(tenant_id="shop", operation_id="op-1", response_class="generated_ai", units=1)
    _on(monkeypatch, "charge_on_delivery")
    settle_after_send(tenant_id="shop", operation_id="op-1", accepted=True, channel="web_chat", provider_message_id="")
    from services.billing.membership.message_ledger import snapshot

    assert snapshot("shop").remaining == 5
