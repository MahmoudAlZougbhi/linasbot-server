"""Pending request fields and inbound Brain ids stay bound across turns."""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from services.customer_ai.actions.pending import attach_confirmation, try_confirm_pending
from services.customer_ai.actions.request_fields import merge_proposal_fields_with_prior
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.turn import ConversationState, CustomerTurn, HistorySnapshot
from services.customer_ai.conversation_store import (
    hydrate_turn_state,
    load_conversation,
    reset_conversation_store_for_tests,
    save_conversation,
)
from services.customer_ai.history_ids import bind_dm_ids, web_inbound_message_id


@pytest.fixture(autouse=True)
def _memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_conversation_store_for_tests()
    yield
    reset_conversation_store_for_tests()


def test_merge_keeps_prior_answers_and_lets_incoming_win() -> None:
    prior = [
        {
            "action_type": "start_request",
            "fields": {"request_type": "APPOINTMENT", "collected_fields": {"name": "Sara", "date": ""}},
        }
    ]
    merged = merge_proposal_fields_with_prior(
        {"request_type": "APPOINTMENT", "collected_fields": {"name": "", "date": "Tuesday"}},
        prior,
    )
    assert merged["collected_fields"] == {"name": "Sara", "date": "Tuesday"}
    other = merge_proposal_fields_with_prior(
        {"request_type": "ORDER", "collected_fields": {"name": ""}},
        prior,
    )
    assert other["collected_fields"] == {"name": ""}


def test_restage_keeps_prior_collected_fields() -> None:
    first = CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m1"])
    attach_confirmation(
        first,
        ActionProposalSet(
            actions=[
                ActionProposal(
                    task_id="book",
                    action_type="start_request",
                    fields={"request_type": "APPOINTMENT", "collected_fields": {"name": "Sara", "date": ""}},
                )
            ]
        ),
    )
    later = hydrate_turn_state(CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m2"]))
    restaged = attach_confirmation(
        later,
        ActionProposalSet(
            actions=[
                ActionProposal(
                    task_id="book",
                    action_type="start_request",
                    fields={"request_type": "APPOINTMENT", "collected_fields": {"name": "", "date": ""}},
                )
            ]
        ),
    )
    assert restaged.actions[0].fields["collected_fields"]["name"] == "Sara"
    assert later.state.confirmed_fields == ["name"]
    assert later.state.missing_fields == ["date"]
    stored = load_conversation("t1", "c1")
    assert stored is not None
    assert stored["pending"][0]["fields"]["collected_fields"]["name"] == "Sara"
    assert restaged.actions[0].expected_revision == "1"


@pytest.mark.asyncio
async def test_confirm_passes_merged_collected_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_execute(_turn, proposals, message):
        captured["fields"] = proposals.actions[0].fields
        captured["message"] = message
        return [{"action_type": "start_request", "state": "success"}]

    monkeypatch.setattr("services.customer_ai.actions.pending._execute", fake_execute)
    turn = CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m1"])
    attach_confirmation(
        turn,
        ActionProposalSet(
            actions=[
                ActionProposal(
                    task_id="book",
                    action_type="start_request",
                    fields={"request_type": "APPOINTMENT", "collected_fields": {"name": "Sara"}},
                )
            ]
        ),
    )
    later = hydrate_turn_state(CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m2"]))
    result = await try_confirm_pending(later, "yes", "instagram_dm")
    assert result is not None
    assert result.extra["confirmed"] is True
    assert captured["fields"]["collected_fields"]["name"] == "Sara"
    assert captured["fields"]["confirmation_text"] == "yes"


def test_bind_dm_ids_uses_existing_ids_only() -> None:
    conv, mid = bind_dm_ids(conversation_id="ig-thread-1", message_id="wamid.9", message="hi")
    assert conv == "ig-thread-1"
    assert mid == "wamid.9"
    conv, mid = bind_dm_ids(user_id="wa:user1", message="hi")
    assert conv == "wa:user1"
    assert mid == web_inbound_message_id("wa:user1", "hi")
    conv, mid = bind_dm_ids(payload={"wamid": "wamid.payload"}, conversation_id="c1", message="hi")
    assert mid == "wamid.payload"
    assert bind_dm_ids(message="hi") == ("", "")


@pytest.mark.asyncio
async def test_brain_dm_fails_closed_without_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CUSTOMER_BRAIN_ENABLED", "true")
    from services.customer_ai.runtime import run_customer_ai_dm

    monkeypatch.setattr("services.customer_ai.runtime.assert_channel_plan_allowed", lambda *_a, **_k: None)
    monkeypatch.setattr(
        "services.customer_ai.runtime.evaluate_gates",
        lambda *_a, **_k: type("G", (), {"allow": True, "reason": "", "detail": {}})(),
    )
    monkeypatch.setattr("services.customer_ai.runtime.apply_live_control", lambda turn: turn)
    monkeypatch.setattr(
        "services.customer_ai.runtime.load_history_snapshot",
        AsyncMock(return_value=HistorySnapshot()),
    )

    async def boom(*_a, **_k):
        raise AssertionError("billed path must not run without inbound ids")

    monkeypatch.setattr("services.customer_ai.runtime._run_billed", boom)
    outcome = await run_customer_ai_dm(tenant_id="t1", message="hi", channel="instagram_dm")
    assert outcome.stop is True
    assert outcome.reason == "failed_closed"
    assert (outcome.metadata or {}).get("reason") == "inbound_ids_required"


def test_load_conversation_prefers_sql_over_stale_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai import conversation_store as store

    monkeypatch.setattr(store, "_persist_enabled", lambda: True)
    monkeypatch.setattr(store, "_persist_pg", lambda *_a, **_k: None)
    monkeypatch.setattr(store, "_load_disk", lambda _key: None)
    store._MEMORY["shop:c-pending"] = {
        "state": {"greeted": False},
        "pending": [{"task_id": "stale"}],
        "history": [{"id": "stale-hist"}],
    }
    monkeypatch.setattr(
        store,
        "_load_pg",
        lambda _key: {
            "state": {"greeted": True},
            "pending": [{"task_id": "book"}],
            "history": [{"id": "sql-hist"}],
        },
    )
    raw = load_conversation("shop", "c-pending")
    assert raw is not None
    assert raw["state"]["greeted"] is True
    assert raw["pending"][0]["task_id"] == "book"
    turn = hydrate_turn_state(CustomerTurn(tenant_id="shop", conversation_id="c-pending"))
    assert turn.state.greeted is True
    assert turn.extra["pending_actions"][0]["task_id"] == "book"


def test_save_conversation_keeps_sql_history_when_memory_stale(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai import conversation_store as store

    monkeypatch.setattr(store, "_persist_enabled", lambda: True)
    monkeypatch.setattr(store, "_persist_pg", lambda *_a, **_k: None)
    monkeypatch.setattr(store, "_load_disk", lambda _key: None)
    store._MEMORY["shop:c-hist"] = {
        "state": {"greeted": False},
        "pending": [],
        "history": [{"id": "stale-hist"}],
    }
    monkeypatch.setattr(
        store,
        "_load_pg",
        lambda _key: {
            "state": {"greeted": True},
            "pending": [],
            "history": [{"id": "sql-hist", "text": "yes"}],
        },
    )
    save_conversation("shop", "c-hist", ConversationState(greeted=True), [{"task_id": "book"}])
    kept = store._MEMORY["shop:c-hist"]
    assert kept["pending"][0]["task_id"] == "book"
    assert kept["history"][0]["id"] == "sql-hist"


def test_load_conversation_sql_miss_does_not_revive_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai import conversation_store as store

    monkeypatch.setattr(store, "_persist_enabled", lambda: True)
    monkeypatch.setattr(store, "_sql_ready", lambda: True)
    monkeypatch.setattr(store, "_load_pg", lambda _key: None)
    monkeypatch.setattr(store, "_load_disk", lambda _key: None)
    store._MEMORY["shop:c-gone"] = {
        "state": {"greeted": True},
        "pending": [{"task_id": "stale-yes"}],
        "history": [{"id": "stale-hist"}],
    }
    assert load_conversation("shop", "c-gone") is None
    turn = hydrate_turn_state(CustomerTurn(tenant_id="shop", conversation_id="c-gone"))
    assert turn.state.greeted is False
    assert turn.extra.get("pending_actions") in (None, [])


def test_save_conversation_sql_miss_does_not_copy_stale_history(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_ai import conversation_store as store

    monkeypatch.setattr(store, "_persist_enabled", lambda: True)
    monkeypatch.setattr(store, "_sql_ready", lambda: True)
    monkeypatch.setattr(store, "_load_pg", lambda _key: None)
    monkeypatch.setattr(store, "_load_disk", lambda _key: None)
    monkeypatch.setattr(store, "_persist_pg", lambda *_a, **_k: None)
    store._MEMORY["shop:c-new"] = {
        "state": {"greeted": True},
        "pending": [{"task_id": "stale-yes"}],
        "history": [{"id": "stale-hist"}],
    }
    save_conversation("shop", "c-new", ConversationState(greeted=True), [{"task_id": "book"}])
    kept = store._MEMORY["shop:c-new"]
    assert kept["pending"][0]["task_id"] == "book"
    assert kept["history"] == []
