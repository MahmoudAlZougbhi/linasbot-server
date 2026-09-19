"""Request continuity: same pending draft, collected_fields, no nag, no second start."""

from __future__ import annotations

from typing import Any

import pytest

from services.brain.actions.pending import try_confirm_pending
from services.brain.agent.request_policy import policy_notes_for_turn, request_policy_notes
from services.brain.agent.request_snapshot import build_request_snapshot
from services.brain.contracts.evidence import EvidenceBundle, EvidenceItem
from services.brain.contracts.turn import CustomerTurn
from services.brain.conversation_store import hydrate_turn_state, load_conversation, reset_conversation_store_for_tests
from services.brain.generate.reply import generate_grounded_reply
from services.brain.tools.registry import execute_tool
from tests.plan_builders import explicit_plan

_HINT_TENANT = "t-cont"
_CONV = "c-cont"
_PUBLISHED = {
    "module_enabled": True,
    "rules": [
        {
            "id": "appt1",
            "type": "APPOINTMENT",
            "name": "Booking",
            "enabled": True,
            "required_fields": ["name", "phone", "preferred_date"],
            "notes": "Collect name, phone, and date.",
        }
    ],
}


@pytest.fixture(autouse=True)
def _memory_and_graph(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_MESSAGE_STORE", "memory")
    reset_conversation_store_for_tests()
    monkeypatch.setattr("services.requests.config_loader.requests_capture_active", lambda *_a, **_k: True)
    monkeypatch.setattr("services.brain.agent.request_snapshot.requests_capture_active", lambda *_a, **_k: True)
    monkeypatch.setattr(
        "services.requests.config_loader.load_published_requests_config",
        lambda *_a, **_k: dict(_PUBLISHED),
    )
    yield
    reset_conversation_store_for_tests()


def _turn(event_id: str) -> CustomerTurn:
    return hydrate_turn_state(
        CustomerTurn(
            tenant_id=_HINT_TENANT,
            conversation_id=_CONV,
            customer_id="u-cont",
            event_ids=[event_id],
            channel="whatsapp",
        )
    )


def _pending_collected(turn: CustomerTurn) -> dict[str, Any]:
    snap = build_request_snapshot(turn)
    pending = snap["pending_confirmation"]
    assert pending, snap
    return dict(pending[0].get("collected") or {})


def _policy_blob(turn: CustomerTurn) -> str:
    snap = build_request_snapshot(turn)
    extra = dict(turn.extra or {})
    extra["request_state"] = {**snap, "module_enabled": True}
    extra["awaiting_confirmation"] = True
    turn.extra = extra
    return "\n".join(policy_notes_for_turn(turn))


@pytest.mark.asyncio
async def test_six_turn_appointment_survives_side_questions() -> None:
    t1 = _turn("m1")
    started = await execute_tool(
        "start_request",
        {
            "request_type": "APPOINTMENT",
            "title": "موعد",
            "fields": {"request_type": "APPOINTMENT", "collected_fields": {}},
        },
        t1,
    )
    assert started.get("ok") is True
    assert (started.get("data") or {}).get("awaiting_confirmation") is True

    t2 = _turn("m2")
    updated = await execute_tool(
        "update_request_draft",
        {
            "fields": {
                "request_type": "APPOINTMENT",
                "collected_fields": {"name": "محمود", "phone": "03xxxxxx"},
            }
        },
        t2,
    )
    assert updated.get("ok") is True
    collected = _pending_collected(t2)
    assert collected["name"] == "محمود"
    assert collected["phone"] == "03xxxxxx"
    snap2 = build_request_snapshot(t2)
    assert "preferred_date" in (snap2["pending_confirmation"][0].get("missing_fields") or [])

    t3 = _turn("m3")
    idle = await execute_tool("no_request_action", {}, t3)
    assert idle.get("ok") is True
    after_price = _pending_collected(t3)
    assert after_price["name"] == "محمود"
    assert after_price["phone"] == "03xxxxxx"
    blob = _policy_blob(t3)
    assert "Ask to confirm" not in blob
    assert "REQUEST_NAG_POLICY" in blob
    assert "Do not chase missing fields" in blob or "do not chase missing fields" in blob.lower()

    t4 = _turn("m4")
    await execute_tool("no_request_action", {}, t4)
    stored = load_conversation(_HINT_TENANT, _CONV) or {}
    assert len(stored.get("pending") or []) == 1
    assert _pending_collected(t4)["name"] == "محمود"

    t5 = _turn("m5")
    again = await execute_tool(
        "start_request",
        {"request_type": "APPOINTMENT", "title": "موعد جديد", "fields": {"request_type": "APPOINTMENT"}},
        t5,
    )
    assert (again.get("data") or {}).get("resumed") is True
    assert len((load_conversation(_HINT_TENANT, _CONV) or {}).get("pending") or []) == 1
    assert _pending_collected(t5)["name"] == "محمود"
    assert _pending_collected(t5)["phone"] == "03xxxxxx"

    t6 = _turn("m6")
    await execute_tool(
        "update_request_draft",
        {"fields": {"request_type": "APPOINTMENT", "collected_fields": {"preferred_date": "بكرا"}}},
        t6,
    )
    final = _pending_collected(t6)
    assert final["name"] == "محمود"
    assert final["phone"] == "03xxxxxx"
    assert final["preferred_date"] == "بكرا"
    assert len((load_conversation(_HINT_TENANT, _CONV) or {}).get("pending") or []) == 1


@pytest.mark.asyncio
async def test_side_question_generate_policy_does_not_nag(monkeypatch: pytest.MonkeyPatch) -> None:
    turn = _turn("g1")
    await execute_tool(
        "start_request",
        {
            "request_type": "APPOINTMENT",
            "fields": {"request_type": "APPOINTMENT", "collected_fields": {"name": "محمود", "phone": "03xxxxxx"}},
        },
        turn,
    )
    turn = _turn("g2")
    turn.extra = {
        **dict(turn.extra or {}),
        "request_state": {**build_request_snapshot(turn), "module_enabled": True},
        "awaiting_confirmation": True,
    }
    captured: dict[str, str] = {}
    from services.brain.compose import blocks as compose_blocks

    original = compose_blocks.compose_evidence_context

    def spy(**kwargs: Any):
        captured["policy"] = "\n".join(kwargs.get("policy_notes") or [])
        return original(**kwargs)

    monkeypatch.setattr("services.brain.generate.reply.compose_evidence_context", spy)
    monkeypatch.setattr("services.brain.generate.reply.openai_configured", lambda: True)

    async def fake_ask(**_k: Any) -> str:
        return "The laser is 50 USD."

    monkeypatch.setattr("services.brain.generate.reply._ask_model", fake_ask)
    bundle = EvidenceBundle(
        outcome="found",
        items=[
            EvidenceItem(
                evidence_id="p1",
                source_family="prices",
                source_id="p1",
                title="Prices",
                text="The laser is 50 USD.",
            )
        ],
    )
    envelope = await generate_grounded_reply(
        turn=turn,
        message="قديش سعر الخدمة؟",
        plan=explicit_plan("قديش سعر الخدمة؟", ("information", ["prices", "services"])),
        bundle=bundle,
        identity=None,
        destination="dm",
        receipts=[],
    )
    assert envelope is not None
    assert envelope.decision == "reply"
    assert "50 USD" in (envelope.messages[0].text if envelope.messages else "")
    assert "Ask to confirm" not in captured.get("policy", "")
    assert "REQUEST_NAG_POLICY" in captured.get("policy", "")
    assert _pending_collected(turn)["name"] == "محمود"


@pytest.mark.asyncio
async def test_confirm_persists_merged_collected_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    async def fake_execute(_turn: CustomerTurn, proposals: Any, message: str) -> list[dict[str, str]]:
        captured["fields"] = proposals.actions[0].fields
        captured["message"] = message
        return [{"action_type": "start_request", "state": "success"}]

    monkeypatch.setattr("services.brain.actions.pending._execute", fake_execute)
    turn = _turn("c1")
    await execute_tool(
        "start_request",
        {
            "request_type": "APPOINTMENT",
            "fields": {
                "request_type": "APPOINTMENT",
                "collected_fields": {"name": "محمود", "phone": "03xxxxxx", "preferred_date": "بكرا"},
            },
        },
        turn,
    )
    later = _turn("c2")
    result = await try_confirm_pending(later, "yes", "whatsapp")
    assert result is not None
    assert result.extra.get("confirmed") is True
    assert captured["fields"]["collected_fields"]["name"] == "محمود"
    assert captured["fields"]["collected_fields"]["preferred_date"] == "بكرا"
    assert (load_conversation(_HINT_TENANT, _CONV) or {}).get("pending") == []


def test_nag_policy_is_canonical() -> None:
    notes = request_policy_notes(
        {
            "module_enabled": True,
            "pending_confirmation": [{"request_type": "APPOINTMENT", "collected": {"name": "Ali"}}],
            "active_drafts": [],
            "past_requests": [],
        }
    )
    blob = "\n".join(notes)
    assert "answer that question first" in blob.lower()
    assert "Ask to confirm" not in blob
    assert "never start a second draft" in blob.lower()
