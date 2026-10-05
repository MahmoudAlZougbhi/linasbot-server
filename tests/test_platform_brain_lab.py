"""Platform-owner brain desk uses the selected tenant and does not charge it."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from services.dashboard.dashboard_session_service import (
    CSRF_COOKIE_NAME,
    CSRF_HEADER_NAME,
    SESSION_COOKIE_NAME,
    session_service,
)


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(
        "services.team.platform_owner_service.platform_owner_service.log_action",
        lambda **_kwargs: None,
    )
    import modules.platform_brain_lab_api  # noqa: F401
    from modules.core import app

    return TestClient(app)


def _owner(client: TestClient) -> None:
    rec = session_service.create_session(
        user_id="platform-1",
        email="owner@example.com",
        role="platform_owner",
        permissions=None,
        tenant_id="platform",
    )
    client.cookies.set(SESSION_COOKIE_NAME, session_service.cookie_value_for(rec))
    client.cookies.set(CSRF_COOKIE_NAME, rec.csrf_token)
    client.headers[CSRF_HEADER_NAME] = rec.csrf_token


def test_customer_lab_uses_selected_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_dm(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(stop=False, reply="أهلا", reason="")

    monkeypatch.setattr("services.team.user_service.user_service.get_users_for_tenant", lambda tid: [{"id": "u"}])
    monkeypatch.setattr("services.brain.reply.orchestrator.run_customer_reply_v2_dm", fake_dm)

    import asyncio

    from services.owner_portal.platform_brain_lab import customer_lab_turn

    result = asyncio.run(
        customer_lab_turn(
            actor_user_id="platform-1",
            tenant_id="shop-a",
            message="بدي سعر",
            history=[{"role": "user", "text": "مرحبا"}, {"role": "assistant", "text": "أهلين"}],
        )
    )
    assert result["reply"] == "أهلا"
    assert captured["tenant_id"] == "shop-a"
    assert captured["channel"] == "instagram_dm"
    assert captured["apply_customer_usage_limits"] is False
    assert captured["conversation_id"] == "lab:platform:platform-1:shop-a:customer"
    assert captured["injected_history"][0]["text"] == "مرحبا"
    assert captured["user_id"] == "platform-lab:platform-1"


def test_copilot_lab_uses_selected_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    async def fake_turn(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(reply_text="منشور المحل جاهز", route=None, pending_confirmation=None)

    monkeypatch.setattr("services.team.user_service.user_service.get_users_for_tenant", lambda tid: [{"id": "u"}])
    monkeypatch.setattr("services.owner_copilot.brain_run.run_owner_turn_v2", fake_turn)

    import asyncio

    from services.owner_portal.platform_brain_lab import copilot_lab_turn

    result = asyncio.run(copilot_lab_turn(actor_user_id="platform-1", tenant_id="shop-b", message="شو ساعات الشغل"))
    assert result["reply"] == "منشور المحل جاهز"
    assert captured["tenant_id"] == "shop-b"
    assert captured["role"] == "owner"
    assert captured["confirm_tool"] is None
    assert captured["conversation_id"] == "lab:platform:platform-1:shop-b:copilot"
    assert captured["messages"][-1] == {"role": "user", "content": "شو ساعات الشغل"}


def test_unknown_tenant_is_not_a_brain(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("services.team.user_service.user_service.get_users_for_tenant", lambda tid: [])
    _owner(client)
    res = client.post("/api/platform/brains/customer", json={"tenant_id": "missing", "message": "hi"})
    assert res.status_code == 404
    assert res.json()["detail"] == "unknown_tenant"


def test_customer_route_reaches_selected_brain(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_dm(**kwargs):
        assert kwargs["tenant_id"] == "shop-a"
        return SimpleNamespace(stop=False, reply="رد التينانت", reason="")

    monkeypatch.setattr("services.team.user_service.user_service.get_users_for_tenant", lambda tid: [{"id": "u"}])
    monkeypatch.setattr("services.brain.reply.orchestrator.run_customer_reply_v2_dm", fake_dm)
    _owner(client)
    res = client.post(
        "/api/platform/brains/customer",
        json={"tenant_id": "shop-a", "message": "مرحبا", "history": []},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["reply"] == "رد التينانت"
    assert body["tenant_id"] == "shop-a"


def test_platform_lab_copilot_does_not_reserve(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*_args, **_kwargs):
        raise AssertionError("reserve")

    monkeypatch.setattr("services.billing.membership.message_ledger.reserve", boom)
    from services.owner_copilot.message_billing import owner_turn_hold_begin

    hold = owner_turn_hold_begin("shop-a", conversation_id="lab:platform:u1:shop-a:copilot", user_text="hi")
    assert hold.blocked is False
    assert hold.units == 0
    assert hold._finalized is True


def test_platform_desk_does_not_journal_provider_expense(monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[str] = []
    monkeypatch.setattr(
        "services.brain.billing._record_pending_llm",
        lambda *_args, **_kwargs: called.append("recorded"),
    )
    from services.brain.billing import apply_message_billing
    from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
    from services.brain.contracts.turn import CustomerTurn

    apply_message_billing(
        CustomerTurn(
            tenant_id="shop-a",
            conversation_id="lab:platform:u1:shop-a:customer",
            event_ids=["desk-1"],
        ),
        TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="dm", text="hi")],
            ),
            ai_called=True,
            extra={"phase": "generate"},
        ),
    )
    assert called == []


def test_lab_usage_is_not_written_on_the_tenant() -> None:
    from services.owner_copilot.models import OwnerV2TurnResult
    from services.owner_copilot.turn_results import record_owner_v2_usage

    record_owner_v2_usage(
        {"tenant_id": "shop-a", "user_id": "platform-lab:u1", "conversation_id": "lab:platform:u1:shop-a:copilot"},
        OwnerV2TurnResult(reply_text="hi"),
    )
