"""Brain request persist must keep the real source channel."""

from __future__ import annotations

from contextlib import contextmanager

import pytest

from services.customer_ai.actions.pending import _confirm_reply, attach_confirmation, try_confirm_pending
from services.customer_ai.actions.requests import persist_request, request_source_channel
from services.customer_ai.contracts.actions import ActionProposal, ActionProposalSet
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.conversation_store import hydrate_turn_state, reset_conversation_store_for_tests
from services.requests.ai_tool import build_context_from_user_data
from services.requests.capture import normalize_source_channel
from services.requests.constants import SOURCE_CHANNEL_WEB_CHAT, SOURCE_CHANNELS


@pytest.fixture(autouse=True)
def _memory_store(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_conversation_store_for_tests()
    yield
    reset_conversation_store_for_tests()


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


def test_request_source_channel_keeps_web_and_rejects_tiktok() -> None:
    assert request_source_channel("web_chat") == SOURCE_CHANNEL_WEB_CHAT
    assert request_source_channel("web") == SOURCE_CHANNEL_WEB_CHAT
    assert request_source_channel("instagram") == "instagram_dm"
    assert request_source_channel("instagram_comment") == "comment_linked_dm"
    assert request_source_channel("tiktok") is None
    assert normalize_source_channel("website") == SOURCE_CHANNEL_WEB_CHAT
    assert SOURCE_CHANNEL_WEB_CHAT in SOURCE_CHANNELS
    web_ctx = build_context_from_user_data({"tenant_id": "shop", "channel": "web_chat"})
    assert web_ctx is not None
    assert web_ctx.source_channel == "web_chat"
    comment_ctx = build_context_from_user_data({"tenant_id": "shop", "channel": "instagram_comment"})
    assert comment_ctx is not None
    assert comment_ctx.source_channel == "comment_linked_dm"
    assert comment_ctx.public_comment is True
    assert build_context_from_user_data({"tenant_id": "shop", "channel": "tiktok"}) is None


def test_persist_request_keeps_web_chat(req_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.requests.service import CustomerRequestsService

    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _tid: "v-web")
    receipt = persist_request(
        session=req_db,
        tenant_id="shop-web",
        proposal=ActionProposal(
            task_id="laser",
            action_type="start_request",
            expected_revision="1",
            confirmation_message_id="m1",
            fields={"request_type": "APPOINTMENT", "title": "Laser", "confirmation_text": "yes"},
        ),
        channel="web_chat",
        customer_id="visitor-1",
        conversation_id="web:shop-web:sess1",
        message_id="m2",
        customer_text="yes",
        current_revision="1",
    )
    assert receipt.state == "success"
    row = CustomerRequestsService(req_db).repo.get_for_tenant(
        tenant_id="shop-web",
        request_id=receipt.backend_id,
    )
    assert row is not None
    assert row.source_channel == "web_chat"


def test_persist_request_remerges_published_graph_keys(req_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.requests.service import CustomerRequestsService

    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _tid: "v-web")
    monkeypatch.setattr(
        "services.customer_ai.actions.requests.merge_fields_for_persist",
        lambda _tid, _kind, collected: {**{"name": "", "date": ""}, **dict(collected or {})},
    )
    receipt = persist_request(
        session=req_db,
        tenant_id="shop-merge",
        proposal=ActionProposal(
            task_id="laser",
            action_type="start_request",
            expected_revision="1",
            confirmation_message_id="m1",
            fields={
                "request_type": "APPOINTMENT",
                "title": "Laser",
                "confirmation_text": "yes",
                "collected_fields": {"name": "Ada"},
            },
        ),
        channel="web_chat",
        customer_id="visitor-1",
        conversation_id="web:shop-merge:sess1",
        message_id="m2",
        customer_text="yes",
        current_revision="1",
    )
    assert receipt.state == "success"
    row = CustomerRequestsService(req_db).repo.get_for_tenant(
        tenant_id="shop-merge",
        request_id=receipt.backend_id,
    )
    assert row is not None
    assert row.collected_fields == {"name": "Ada", "date": ""}


def test_persist_request_rejects_unknown_tiktok_source(req_db) -> None:
    receipt = persist_request(
        session=req_db,
        tenant_id="shop-tt",
        proposal=ActionProposal(
            task_id="laser",
            action_type="start_request",
            expected_revision="1",
            confirmation_message_id="m1",
            fields={"request_type": "APPOINTMENT", "confirmation_text": "yes"},
        ),
        channel="tiktok",
        customer_id="open-id",
        conversation_id="ttconv_12345678",
        message_id="m2",
        customer_text="yes",
        current_revision="1",
    )
    assert receipt.state == "rejected"
    assert receipt.reason == "invalid_source_channel"


def test_confirm_reply_is_honest_for_unknown_channel() -> None:
    text = _confirm_reply(False, [{"reason": "invalid_source_channel"}])
    assert "cannot submit" in text.lower()
    assert "try again" not in text.lower()


@pytest.mark.asyncio
async def test_yes_from_web_chat_persists_web_source(req_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from db.session import whatsapp_session
    from services.requests.service import CustomerRequestsService

    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _tid: "v-web")
    first = CustomerTurn(
        tenant_id="shop-web",
        conversation_id="web:shop-web:sess1",
        customer_id="visitor-1",
        channel="web_chat",
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
            tenant_id="shop-web",
            conversation_id="web:shop-web:sess1",
            customer_id="visitor-1",
            channel="web_chat",
            event_ids=["m2"],
        )
    )
    result = await try_confirm_pending(second, "yes", "web_chat")
    assert result is not None
    assert result.extra["confirmed"] is True
    backend_id = result.extra["receipts"][0]["backend_id"]
    with whatsapp_session(require=False) as session:
        row = CustomerRequestsService(session).repo.get_for_tenant(tenant_id="shop-web", request_id=backend_id)
        assert row is not None
        assert row.source_channel == "web_chat"
    _ = req_db


@pytest.mark.asyncio
async def test_empty_turn_channel_binds_live_channel(req_db, monkeypatch: pytest.MonkeyPatch) -> None:
    from db.session import whatsapp_session
    from services.requests.service import CustomerRequestsService

    monkeypatch.setattr("services.requests.service.requests_capture_active", lambda _tid: True)
    monkeypatch.setattr("services.requests.service.published_configuration_version", lambda _tid: "v-ig")
    first = CustomerTurn(tenant_id="shop-ig", conversation_id="c-ig", event_ids=["m1"])
    attach_confirmation(
        first,
        ActionProposalSet(
            actions=[ActionProposal(task_id="t", action_type="start_request", fields={"request_type": "APPOINTMENT"})]
        ),
    )
    second = hydrate_turn_state(CustomerTurn(tenant_id="shop-ig", conversation_id="c-ig", event_ids=["m2"]))
    result = await try_confirm_pending(second, "yes", "instagram_dm")
    assert result is not None
    assert result.extra["confirmed"] is True
    backend_id = result.extra["receipts"][0]["backend_id"]
    with whatsapp_session(require=False) as session:
        row = CustomerRequestsService(session).repo.get_for_tenant(tenant_id="shop-ig", request_id=backend_id)
        assert row is not None
        assert row.source_channel == "instagram_dm"
    _ = req_db


@pytest.mark.asyncio
async def test_yes_from_tiktok_explains_unsupported_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    @contextmanager
    def fake_session(*, require: bool = False):
        _ = require
        yield object()

    monkeypatch.setattr("db.session.whatsapp_session", fake_session)
    first = CustomerTurn(
        tenant_id="shop-tt",
        conversation_id="ttconv_12345678",
        channel="tiktok",
        event_ids=["m1"],
    )
    attach_confirmation(
        first,
        ActionProposalSet(
            actions=[ActionProposal(task_id="t", action_type="start_request", fields={"request_type": "APPOINTMENT"})]
        ),
    )
    second = hydrate_turn_state(
        CustomerTurn(tenant_id="shop-tt", conversation_id="ttconv_12345678", channel="tiktok", event_ids=["m2"])
    )
    result = await try_confirm_pending(second, "yes", "tiktok")
    assert result is not None
    assert result.extra["confirmed"] is False
    assert "cannot submit" in result.envelope.messages[0].text.lower()
