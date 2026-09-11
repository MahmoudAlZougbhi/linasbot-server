"""Conversation state and pending request confirmation across turns."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.customer_ai.actions.confirm import confirmation_valid
from services.customer_ai.actions.pending import attach_confirmation, try_confirm_pending
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.plan import PlannerPlan, PlannerTask, TaskSpan
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.customer_ai.contracts.turn import ConversationState, CustomerTurn
from services.customer_ai.conversation_history import (
    append_visible_history,
    load_stored_history_rows,
    record_turn_history,
)
from services.customer_ai.conversation_store import (
    hydrate_turn_state,
    load_conversation,
    remember_turn,
    reset_conversation_store_for_tests,
    save_conversation,
)
from services.customer_ai.history_ids import (
    conversation_id_for_brain,
    conversation_id_from_user_data,
    message_id_for_brain,
    web_inbound_message_id,
)
from services.customer_ai.history_store import load_history_snapshot
from services.customer_ai.history_tiktok import provider_conversation_id, rows_from_tt_messages
from services.customer_ai.history_web import rows_from_web_messages, session_id_from_conversation
from services.customer_ai.turn_pipeline import run_dm_after_gates


@pytest.fixture(autouse=True)
def _memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_conversation_store_for_tests()
    yield
    reset_conversation_store_for_tests()


def test_conversation_state_roundtrip() -> None:
    save_conversation(
        "t1",
        "c1",
        ConversationState(greeted=True, draft_revision="1"),
        [{"task_id": "a", "action_type": "start_request"}],
    )
    raw = load_conversation("t1", "c1")
    assert raw is not None
    assert raw["state"]["greeted"] is True
    turn = hydrate_turn_state(CustomerTurn(tenant_id="t1", conversation_id="c1"))
    assert turn.state.greeted is True
    assert turn.state.draft_revision == "1"
    assert turn.extra["pending_actions"][0]["task_id"] == "a"


def test_conversation_store_file_roundtrip(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LINAS_MESSAGE_STORE", raising=False)
    monkeypatch.delenv("LINAS_BILLING_BACKEND", raising=False)
    monkeypatch.delenv("LINAS_WHATSAPP_DATABASE_URL", raising=False)
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    reset_conversation_store_for_tests()
    save_conversation("shop", "web:shop:visitor12", ConversationState(greeted=True), [])
    reset_conversation_store_for_tests()
    raw = load_conversation("shop", "web:shop:visitor12")
    assert raw is not None
    assert raw["state"]["greeted"] is True


def test_remember_turn_preserves_stored_history() -> None:
    append_visible_history("t1", "c1", [{"id": "m1", "role": "user", "text": "hi"}])
    remember_turn(CustomerTurn(tenant_id="t1", conversation_id="c1", state=ConversationState(greeted=True)))
    rows = load_stored_history_rows("t1", "c1")
    assert rows[0]["text"] == "hi"
    assert load_conversation("t1", "c1")["state"]["greeted"] is True


def test_comment_history_skips_private_dm() -> None:
    turn = CustomerTurn(tenant_id="t1", conversation_id="comment:t1:instagram_comment:p1")
    record_turn_history(
        turn,
        inbound_id="c9",
        inbound_text="price?",
        result=TurnResult(
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[
                    OutboundMessage(destination="dm", text="Sent you a DM.", idempotency_key="priv"),
                    OutboundMessage(destination="comment", text="Public reply", idempotency_key="pub"),
                ],
            )
        ),
        comment_surface=True,
    )
    texts = [row["text"] for row in load_stored_history_rows("t1", turn.conversation_id)]
    assert "price?" in texts
    assert "Public reply" in texts
    assert "Sent you a DM." not in texts


@pytest.mark.asyncio
async def test_history_store_uses_conversation_store_when_channels_miss(monkeypatch: pytest.MonkeyPatch) -> None:
    append_visible_history("shop", "ig-thread-abcdef12", [{"id": "old", "role": "user", "text": "earlier"}])

    async def empty_firestore(*_a, **_k):
        return []

    monkeypatch.setattr("utils.utils_context.get_conversation_history_from_firestore", empty_firestore)
    monkeypatch.setattr("services.customer_ai.history_whatsapp.load_whatsapp_history_rows", lambda _cid: [])
    monkeypatch.setattr("services.customer_ai.history_tiktok.load_tiktok_history_rows", lambda _cid: [])
    snap = await load_history_snapshot(
        user_id="u1",
        conversation_id="ig-thread-abcdef12",
        tenant_id="shop",
        current_inbound_id="now",
        current_inbound_text="price?",
    )
    assert [item.text for item in snap.messages] == ["earlier", "price?"]


def test_remember_turn_does_not_restore_cleared_pending() -> None:
    turn = CustomerTurn(tenant_id="t1", conversation_id="c1", extra={"pending_actions": [{"task_id": "stale"}]})
    remember_turn(turn, [])
    remember_turn(turn)
    raw = load_conversation("t1", "c1")
    assert raw is not None
    assert raw["pending"] == []


def test_attach_confirmation_binds_revision_and_inbound() -> None:
    turn = CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m1"])
    out = attach_confirmation(
        turn,
        ActionProposalSet(actions=[ActionProposal(task_id="t", action_type="start_request")]),
    )
    assert turn.state.draft_revision == "1"
    assert out.actions[0].expected_revision == "1"
    assert out.actions[0].confirmation_message_id == "m1"
    stored = load_conversation("t1", "c1")
    assert stored is not None
    assert stored["pending"][0]["confirmation_message_id"] == "m1"


@pytest.mark.asyncio
async def test_try_confirm_ignores_non_yes() -> None:
    turn = CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m1"])
    attach_confirmation(
        turn,
        ActionProposalSet(actions=[ActionProposal(task_id="t", action_type="start_request")]),
    )
    assert await try_confirm_pending(turn, "book tomorrow", "instagram_dm") is None


@pytest.mark.asyncio
async def test_try_confirm_yes_clears_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_execute(turn, proposals, message):
        assert proposals.actions[0].confirmation_message_id == "m1"
        assert message == "yes"
        _ = turn
        return [{"action_type": "start_request", "state": "success", "backend_id": "req1"}]

    monkeypatch.setattr("services.customer_ai.actions.pending._execute", fake_execute)
    turn = CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m1"])
    attach_confirmation(
        turn,
        ActionProposalSet(
            actions=[ActionProposal(task_id="t", action_type="start_request", fields={"request_type": "APPOINTMENT"})]
        ),
    )
    next_turn = hydrate_turn_state(CustomerTurn(tenant_id="t1", conversation_id="c1", event_ids=["m2"]))
    result = await try_confirm_pending(next_turn, "yes", "instagram_dm")
    assert result is not None
    assert result.extra["confirmed"] is True
    assert load_conversation("t1", "c1")["pending"] == []


@pytest.mark.asyncio
async def test_request_confirm_survives_next_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.customer_ai.turn_pipeline._exact_faq_result", lambda *_a, **_k: None)

    async def no_semantic(*_a, **_k):
        return None

    monkeypatch.setattr("services.customer_ai.turn_pipeline._semantic_faq_result", no_semantic)

    async def plan(text, _hist, tenant_id="", **_kwargs):
        _ = tenant_id
        return PlannerPlan(
            read_only=False,
            tasks=[PlannerTask(id="book", type="service_request", span=TaskSpan(text=text))],
        )

    monkeypatch.setattr("services.customer_ai.agent.loop.plan_turn", plan)

    first = CustomerTurn(tenant_id="t1", conversation_id="c-book", event_ids=["m1"])
    staged = await run_dm_after_gates(first, message="book laser", channel="instagram_dm")
    assert staged.extra["awaiting_confirmation"] is True
    assert staged.extra["pending_actions"][0]["expected_revision"] == "1"

    async def fake_execute(turn, proposals, message):
        assert confirmation_valid(
            message_id=proposals.actions[0].confirmation_message_id,
            customer_text=message,
            expected_revision=proposals.actions[0].expected_revision,
            current_revision=turn.state.draft_revision,
        )
        return [{"action_type": "start_request", "state": "success"}]

    monkeypatch.setattr("services.customer_ai.actions.pending._execute", fake_execute)
    second = hydrate_turn_state(CustomerTurn(tenant_id="t1", conversation_id="c-book", event_ids=["m2"]))
    confirmed = await run_dm_after_gates(second, message="yes", channel="instagram_dm")
    assert confirmed.extra["phase"] == "request_confirm"
    assert confirmed.extra["confirmed"] is True
    assert confirmed.envelope.decision == "deterministic"


def test_greeting_flag_survives_next_turn() -> None:
    turn = CustomerTurn(tenant_id="t1", conversation_id="c-hi")
    turn.state = turn.state.model_copy(update={"greeted": True})
    remember_turn(turn)
    later = hydrate_turn_state(CustomerTurn(tenant_id="t1", conversation_id="c-hi"))
    assert later.state.greeted is True


def test_web_history_maps_roles() -> None:
    assert session_id_from_conversation("web:shop:visitor_abc") == "visitor_abc"
    rows = rows_from_web_messages(
        [
            SimpleNamespace(id="1", role="visitor", content="hi", created_at=None),
            SimpleNamespace(id="2", role="assistant", content="hello", created_at=None),
        ]
    )
    assert rows[0]["role"] == "user"
    assert rows[0]["text"] == "hi"
    assert rows[1]["role"] == "assistant"
    assert rows[1]["text"] == "hello"


@pytest.mark.asyncio
async def test_history_store_web_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def empty_firestore(*_a, **_k):
        return []

    monkeypatch.setattr("utils.utils_context.get_conversation_history_from_firestore", empty_firestore)
    monkeypatch.setattr("services.customer_ai.history_whatsapp.load_whatsapp_history_rows", lambda _cid: [])
    monkeypatch.setattr(
        "services.customer_ai.history_web.load_web_history_rows",
        lambda cid: [{"id": "w1", "role": "user", "text": f"from-{cid}", "visible_to_customer": True}],
    )
    snap = await load_history_snapshot(user_id="u1", conversation_id="web:t:session12")
    assert snap.messages[0].text == "from-web:t:session12"


@pytest.fixture()
def req_db(tmp_path, monkeypatch: pytest.MonkeyPatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from db.models import Base
    from db.session import reset_engine_for_tests

    url = f"sqlite:///{tmp_path / 'requests.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()
    yield session
    session.close()
    reset_engine_for_tests()


@pytest.mark.asyncio
async def test_yes_persists_request_when_db_is_up(req_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from db.session import whatsapp_session
    from services.requests.service import CustomerRequestsService

    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _tid: "v-test")
    first = CustomerTurn(
        tenant_id="t-book",
        conversation_id="c-book",
        customer_id="cust1",
        channel="instagram_dm",
        event_ids=["m1"],
    )
    attach_confirmation(
        first,
        ActionProposalSet(
            actions=[
                ActionProposal(
                    task_id="laser",
                    action_type="start_request",
                    fields={"request_type": "APPOINTMENT", "title": "Laser consult"},
                )
            ]
        ),
    )
    second = hydrate_turn_state(
        CustomerTurn(
            tenant_id="t-book",
            conversation_id="c-book",
            customer_id="cust1",
            channel="instagram_dm",
            event_ids=["m2"],
        )
    )
    result = await try_confirm_pending(second, "yes", "instagram_dm")
    assert result is not None
    assert result.extra["confirmed"] is True
    backend_id = result.extra["receipts"][0]["backend_id"]
    assert backend_id
    with whatsapp_session(require=False) as session:
        row = CustomerRequestsService(session).repo.get_for_tenant(tenant_id="t-book", request_id=backend_id)
        assert row is not None
        assert row.title == "Laser consult"
        assert row.configuration_version == "v-test"
    assert load_conversation("t-book", "c-book")["pending"] == []
    _ = req_db


@pytest.mark.asyncio
async def test_yes_explains_when_requests_are_not_set_up(monkeypatch: pytest.MonkeyPatch) -> None:
    from contextlib import contextmanager

    @contextmanager
    def fake_session(*, require: bool = False):
        _ = require
        yield object()

    monkeypatch.setattr("db.session.whatsapp_session", fake_session)
    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: False)
    first = CustomerTurn(tenant_id="t-setup", conversation_id="c-setup", channel="instagram_dm", event_ids=["m1"])
    attach_confirmation(
        first,
        ActionProposalSet(
            actions=[ActionProposal(task_id="t", action_type="start_request", fields={"request_type": "APPOINTMENT"})]
        ),
    )
    second = hydrate_turn_state(
        CustomerTurn(tenant_id="t-setup", conversation_id="c-setup", channel="instagram_dm", event_ids=["m2"])
    )
    result = await try_confirm_pending(second, "yes", "instagram_dm")
    assert result is not None
    assert result.extra["confirmed"] is False
    assert "request setup" in result.envelope.messages[0].text.lower()
    assert load_conversation("t-setup", "c-setup")["pending"]


@pytest.mark.asyncio
async def test_history_store_skips_web_for_instagram(monkeypatch: pytest.MonkeyPatch) -> None:
    called = {"web": False}

    async def empty_firestore(*_a, **_k):
        return []

    def mark_web(_cid: str):
        called["web"] = True
        return []

    monkeypatch.setattr("utils.utils_context.get_conversation_history_from_firestore", empty_firestore)

    def mark_wa(_cid: str):
        called["wa"] = True
        return [{"id": "wa1", "role": "user", "text": "from-wa", "visible_to_customer": True}]

    monkeypatch.setattr("services.customer_ai.history_whatsapp.load_whatsapp_history_rows", mark_wa)
    monkeypatch.setattr("services.customer_ai.history_web.load_web_history_rows", mark_web)
    monkeypatch.setattr("services.customer_ai.history_tiktok.load_tiktok_history_rows", lambda _cid: [])
    snap = await load_history_snapshot(
        user_id="u1",
        conversation_id="ig-thread-12345678",
        channel="instagram_dm",
    )
    assert called["web"] is False
    assert called.get("wa") is not True
    assert snap.messages == []


def test_tiktok_history_maps_roles() -> None:
    assert provider_conversation_id("shop:tiktok:ttconv_abcdef12") == "ttconv_abcdef12"
    rows = rows_from_tt_messages(
        [
            SimpleNamespace(id="1", provider_message_id="in1", direction="inbound", text="hi", created_at=None),
            SimpleNamespace(id="2", provider_message_id="out1", direction="outbound", text="hello", created_at=None),
        ]
    )
    assert rows[0]["role"] == "user"
    assert rows[0]["text"] == "hi"
    assert rows[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_history_store_tiktok_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    async def empty_firestore(*_a, **_k):
        return []

    monkeypatch.setattr("utils.utils_context.get_conversation_history_from_firestore", empty_firestore)
    monkeypatch.setattr("services.customer_ai.history_whatsapp.load_whatsapp_history_rows", lambda _cid: [])
    monkeypatch.setattr(
        "services.customer_ai.history_tiktok.load_tiktok_history_rows",
        lambda cid: [{"id": "t1", "role": "user", "text": f"from-{cid}", "visible_to_customer": True}],
    )
    snap = await load_history_snapshot(user_id="u1", conversation_id="ttconv_12345678", channel="tiktok")
    assert snap.messages[0].text == "from-ttconv_12345678"


def test_omni_conversation_id_prefers_payload() -> None:
    assert (
        conversation_id_for_brain(
            payload={"conversation_id": "ttconv_12345678"},
            conversation_key="shop:tiktok:other",
        )
        == "ttconv_12345678"
    )
    assert conversation_id_for_brain(conversation_key="shop:tiktok:ttconv_12345678") == "ttconv_12345678"
    assert (
        conversation_id_for_brain(payload={"current_conversation_id": "ig-thread-1", "channel": "instagram"})
        == "ig-thread-1"
    )
    assert conversation_id_from_user_data({"current_conversation_id": None}, fallback="shop:instagram:igsid") == (
        "shop:instagram:igsid"
    )
    from inspect import getsource

    from handlers.text_handlers_respond_phase2 import text_handlers_respond_phase2

    phase2 = getsource(text_handlers_respond_phase2)
    assert "conversation_id_from_user_data" in phase2
    assert "fallback=str(current_conversation_id or user_id or \"\")" in phase2
    assert message_id_for_brain({"provider_message_id": "mid-9"}) == "mid-9"
    assert message_id_for_brain({"_combine_mid": "mid-ig"}) == "mid-ig"
    assert message_id_for_brain({"_batch_inbound_mids": ["old", "mid-last"]}) == "mid-last"
    assert message_id_for_brain({"provider_message_id": "wamid.abc", "message_id": "local-1"}) == "wamid.abc"
    assert message_id_for_brain({"provider_event_id": "evt-row-1"}) == "evt-row-1"
    assert web_inbound_message_id("web:t:v", "hi").startswith("user:web:t:v:")
    from services.web_chat.processor_v2_reply import generate_web_chat_reply_text

    assert "web_inbound_message_id(conversation_id, text)" in getsource(generate_web_chat_reply_text)


@pytest.mark.asyncio
async def test_omni_generate_passes_conversation_id(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_reply_v2.models import CustomerReplyOutcome
    from services.omnichannel.generate import _generate_canonical

    captured: dict = {}

    async def fake_dm(**kwargs):
        captured.update(kwargs)
        return CustomerReplyOutcome(stop=False, reply="ok", reason="")

    monkeypatch.setattr("services.customer_reply_v2.orchestrator.run_customer_reply_v2_dm", fake_dm)
    monkeypatch.setattr(
        "services.customer_ai.leftover_reserve.reserve_leftover_reply",
        lambda **_k: "res-test",
    )
    text, _res, err = await _generate_canonical(
        channel="instagram",
        surface="dm",
        tenant_id="t1",
        payload={
            "text": "hi",
            "conversation_id": "ig-thread-12345678",
            "sender_id": "s1",
            "provider_message_id": "m9",
        },
        conversation_key="t1:instagram:dm:s1",
    )
    assert err is None
    assert text == "ok"
    assert captured["conversation_id"] == "ig-thread-12345678"
    assert captured["message_id"] == "m9"
    assert captured["user_id"] == "s1"
