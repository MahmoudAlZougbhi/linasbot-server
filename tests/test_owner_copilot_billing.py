"""Owner Copilot message-hold: estimate, confirm, idempotency, insufficient."""

from __future__ import annotations

import pytest

from services.billing.membership.catalog_admin import reset_catalog_admin_for_tests, update_draft
from services.billing.membership.economy_policy import validate_economy
from services.billing.membership.message_ledger import grant_lot, remaining_messages, reset_ledger_for_tests
from services.owner_copilot.message_billing import (
    confirm_copy,
    copilot_operation_id,
    owner_turn_hold_abort,
    owner_turn_hold_begin,
    owner_turn_hold_finalize,
)


@pytest.fixture(autouse=True)
def _ledger_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_ledger_for_tests()
    reset_catalog_admin_for_tests()


def test_confirm_copy_is_localized() -> None:
    assert "10" in confirm_copy(units=10, language="en")
    assert "رسائل" in confirm_copy(units=10, language="ar")
    assert "messages" in confirm_copy(units=10, language="fr")


def test_same_turn_is_idempotent() -> None:
    grant_lot(
        tenant_id="idemp-shop",
        lot_id="idemp-shop:seed",
        kind="purchased",
        period_id="seed",
        amount=20,
        expires=False,
    )
    first = owner_turn_hold_begin(
        "idemp-shop",
        conversation_id="c1",
        user_text="review prices",
        confirm_billing=True,
        estimated_usd=0.01,
    )
    second = owner_turn_hold_begin(
        "idemp-shop",
        conversation_id="c1",
        user_text="review prices",
        confirm_billing=True,
        estimated_usd=0.01,
    )
    assert first.blocked is False
    assert first.operation_id == second.operation_id
    assert first.reservation_id == second.reservation_id
    assert remaining_messages("idemp-shop") == 19
    owner_turn_hold_finalize(first)
    assert remaining_messages("idemp-shop") == 19


def test_retry_after_abort_does_not_double_charge() -> None:
    grant_lot(
        tenant_id="abort-shop",
        lot_id="abort-shop:seed",
        kind="purchased",
        period_id="seed",
        amount=5,
        expires=False,
    )
    first = owner_turn_hold_begin("abort-shop", conversation_id="c1", user_text="hi")
    owner_turn_hold_abort(first)
    assert remaining_messages("abort-shop") == 5
    second = owner_turn_hold_begin("abort-shop", conversation_id="c1", user_text="hi")
    owner_turn_hold_finalize(second)
    assert remaining_messages("abort-shop") == 4


def test_insufficient_payload_includes_required_and_remaining(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.billing.credit_ai_gate import owner_credits_paused_payload

    monkeypatch.setattr("services.billing.credit_ai_gate.remaining_messages", lambda *_a, **_k: 1)
    payload = owner_credits_paused_payload("empty-shop", need=5)
    assert payload["code"] == "insufficient_messages"
    assert payload["required"] == 5
    assert payload["remaining"] == 1
    assert payload["actions"]["buy_messages"] is True
    assert "5" in payload["message"]
    assert "1" in payload["message"]


def test_expensive_band_requires_confirm_then_reserves() -> None:
    grant_lot(
        tenant_id="band-shop",
        lot_id="band-shop:seed",
        kind="purchased",
        period_id="seed",
        amount=20,
        expires=False,
    )
    update_draft(
        actor="test",
        changes={
            "economy": validate_economy(
                {
                    "copilot": {
                        "confirm_threshold_messages": 2,
                        "bands": [{"min_usd": 0, "max_usd": 10, "message_units": 4}],
                    }
                }
            )
        },
        reason="test",
    )
    pending = owner_turn_hold_begin("band-shop", estimated_usd=0.5)
    assert pending.confirm_required is True
    assert pending.units == 4
    held = owner_turn_hold_begin("band-shop", estimated_usd=0.5, confirm_billing=True, user_text="bulk import")
    assert held.confirm_required is False
    assert held.units == 4
    assert remaining_messages("band-shop") == 16


def test_operation_id_changes_when_text_changes() -> None:
    a = copilot_operation_id(tenant_id="t", conversation_id="c", user_text="one")
    b = copilot_operation_id(tenant_id="t", conversation_id="c", user_text="two")
    assert a != b
    assert a.startswith("owner:")


@pytest.mark.asyncio
async def test_stream_emits_billing_confirm_without_sol(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.brain import iter_owner_turn_v2_events
    from services.owner_copilot.message_billing import OwnerTurnHold

    monkeypatch.setattr(
        "services.owner_copilot.message_billing.owner_turn_hold_begin",
        lambda *_a, **_k: OwnerTurnHold(tenant_id="t1", confirm_required=True, units=10),
    )
    called = {"n": 0}

    async def _fake_body(**_kwargs):
        called["n"] += 1
        yield None

    monkeypatch.setattr("services.owner_copilot.brain._iter_owner_turn_v2_events_body", _fake_body)
    events = []
    async for ev in iter_owner_turn_v2_events(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="expensive ingest",
        reply_language="en",
    ):
        events.append(ev)
    assert [ev.type for ev in events] == ["billing_confirm"]
    assert events[0].payload["units"] == 10
    assert "10" in str(events[0].payload.get("message") or "")
    assert called["n"] == 0


def test_default_policy_does_not_confirm_cheap_chat() -> None:
    grant_lot(
        tenant_id="cheap-shop",
        lot_id="cheap-shop:seed",
        kind="purchased",
        period_id="seed",
        amount=10,
        expires=False,
    )
    held = owner_turn_hold_begin("cheap-shop", conversation_id="c1", user_text="hi", estimated_usd=0.01)
    assert held.confirm_required is False
    assert held.blocked is False
    assert held.units == 1


def test_tenant_holds_are_isolated() -> None:
    for tenant in ("iso-a", "iso-b"):
        grant_lot(
            tenant_id=tenant,
            lot_id=f"{tenant}:seed",
            kind="purchased",
            period_id="seed",
            amount=3,
            expires=False,
        )
    a = owner_turn_hold_begin("iso-a", conversation_id="shared", user_text="same")
    b = owner_turn_hold_begin("iso-b", conversation_id="shared", user_text="same")
    assert a.operation_id != b.operation_id
    assert remaining_messages("iso-a") == 2
    assert remaining_messages("iso-b") == 2
    owner_turn_hold_finalize(a)
    assert remaining_messages("iso-a") == 2
    assert remaining_messages("iso-b") == 2


@pytest.mark.asyncio
async def test_error_event_releases_reservation(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.brain import iter_owner_turn_v2_events
    from services.owner_copilot.models import StreamEvent

    grant_lot(
        tenant_id="fail-shop",
        lot_id="fail-shop:seed",
        kind="purchased",
        period_id="seed",
        amount=4,
        expires=False,
    )

    async def _failing_body(**_kwargs):
        yield StreamEvent(type="error", payload={"message": "sol_down"})

    monkeypatch.setattr("services.owner_copilot.brain._iter_owner_turn_v2_events_body", _failing_body)
    events = []
    async for ev in iter_owner_turn_v2_events(
        tenant_id="fail-shop",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="hello",
    ):
        events.append(ev.type)
    assert "error" in events
    from services.billing.membership.message_ledger import snapshot

    assert snapshot("fail-shop").reserved == 0
    assert remaining_messages("fail-shop") == 4


def test_cm_faq_and_approval_tools_remain_registered() -> None:
    from services.owner_copilot.tool_schemas import tool_names

    names = set(tool_names())
    for required in (
        "read_cm",
        "propose_cm_patch",
        "propose_cm_faq_upsert",
        "propose_cm_delete",
        "propose_cm_article_upsert",
        "propose_smart_answer",
        "read_faq_quota",
    ):
        assert required in names


def test_estimate_uses_shared_model_pricing() -> None:
    from services.owner_copilot.message_billing import estimate_copilot_cost_usd

    with_file = estimate_copilot_cost_usd(user_text="hello", history_tokens=100, attachment_count=1)
    chat_only = estimate_copilot_cost_usd(user_text="hello", history_tokens=100, attachment_count=0)
    assert with_file > chat_only > 0


def test_actual_cost_releases_unused_reservation() -> None:
    from services.billing.membership.catalog_admin import update_draft
    from services.billing.membership.economy_policy import validate_economy
    from services.owner_copilot.message_billing import owner_turn_hold_begin, owner_turn_hold_finalize

    grant_lot(
        tenant_id="actual-shop",
        lot_id="actual-shop:seed",
        kind="purchased",
        period_id="seed",
        amount=20,
        expires=False,
    )
    update_draft(
        actor="test",
        changes={
            "economy": validate_economy(
                {
                    "copilot": {
                        "confirm_threshold_messages": 10,
                        "bands": [
                            {"min_usd": 0, "max_usd": 0.01, "message_units": 1},
                            {"min_usd": 0.011, "max_usd": 10, "message_units": 5},
                        ],
                    }
                }
            )
        },
        reason="test",
    )
    held = owner_turn_hold_begin(
        "actual-shop",
        estimated_usd=1.0,
        confirm_billing=True,
        user_text="ingest",
    )
    assert held.units == 5
    assert remaining_messages("actual-shop") == 15
    owner_turn_hold_finalize(held, actual_usd=0.001)
    assert remaining_messages("actual-shop") == 19
