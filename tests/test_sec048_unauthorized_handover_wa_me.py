"""SEC-048: unauthorized human_handover coerce → WhatsApp/wa.me guidance (not operator queue)."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from handlers.text_handlers_respond_phase6 import text_handlers_respond_phase6
from handlers.text_handlers_wa_me_handoff import build_wa_me_handoff_guidance


@pytest.fixture
def wa_me_reply(monkeypatch: pytest.MonkeyPatch) -> str:
    reply = "Contact us on WhatsApp only:\n+96178847527\nhttps://wa.me/96178847527"

    def _fake_guidance(*, user_data: dict[str, Any] | None = None, language: str | None = None) -> str:
        return reply

    monkeypatch.setattr(
        "handlers.text_handlers_respond_phase6.build_wa_me_handoff_guidance",
        _fake_guidance,
    )
    monkeypatch.setattr(
        "handlers.text_handlers_wa_me_handoff.build_wa_me_handoff_guidance",
        _fake_guidance,
    )
    return reply


def _base_ctx(**overrides: Any) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "canonical_user_id": "u1",
        "current_conversation_id": "c1",
        "current_gender": "unknown",
        "current_preferred_lang": "en",
        "db": None,
        "get_canonical_user_id_and_phone": lambda uid, phone: (uid, phone),
        "get_dynamic_message": lambda key, lang: f"dyn:{key}",
        "get_firestore_db": lambda: None,
        "is_post_takeover_escalation_cooldown": lambda user_data: False,
        "user_data": {"tenant_id": "linas", "channel": "whatsapp"},
        "user_id": "u1",
        "user_input_to_process": "how much is laser?",
        "users_coll": None,
        "gpt_response_data": {
            "action": "answer_question",
            "bot_reply": "ok",
            "handover_degree": "none",
            "_flow_meta": {},
        },
    }
    ctx.update(overrides)
    return ctx


@pytest.mark.asyncio
async def test_flow_meta_error_does_not_coerce_human_handover(wa_me_reply: str) -> None:
    ctx = _base_ctx(
        gpt_response_data={
            "action": "answer_question",
            "bot_reply": "partial",
            "handover_degree": "none",
            "_flow_meta": {"error": "openai_timeout"},
        }
    )
    await text_handlers_respond_phase6(ctx)
    assert ctx["action"] == "answer_question"
    assert ctx["action"] != "human_handover"
    assert "wa.me" in (ctx["bot_reply_text"] or "").lower()
    assert ctx["bot_reply_text"] == wa_me_reply


@pytest.mark.asyncio
async def test_bad_action_empty_reply_uses_wa_me_not_queue(wa_me_reply: str) -> None:
    ctx = _base_ctx(
        gpt_response_data={
            "action": "not_a_real_action",
            "bot_reply": "",
            "handover_degree": "none",
            "_flow_meta": {},
        }
    )
    await text_handlers_respond_phase6(ctx)
    assert ctx["action"] == "answer_question"
    assert "wa.me" in (ctx["bot_reply_text"] or "").lower()


@pytest.mark.asyncio
async def test_booking_claim_without_crm_uses_wa_me(wa_me_reply: str) -> None:
    ctx = _base_ctx(
        gpt_response_data={
            "action": "answer_question",
            "bot_reply": "Your appointment has been booked successfully.",
            "handover_degree": "none",
            "_flow_meta": {},
        }
    )
    await text_handlers_respond_phase6(ctx)
    assert ctx["action"] == "answer_question"
    assert "wa.me" in (ctx["bot_reply_text"] or "").lower()


@pytest.mark.asyncio
async def test_booking_claim_capture_active_skips_wa_me_without_false_recorded(
    monkeypatch: pytest.MonkeyPatch,
    wa_me_reply: str,
) -> None:
    monkeypatch.setattr(
        "services.requests.capture.skip_forced_booking_wa_me",
        lambda _tid: True,
    )
    ctx = _base_ctx(
        gpt_response_data={
            "action": "answer_question",
            "bot_reply": "Your appointment has been booked successfully.",
            "handover_degree": "none",
            "_flow_meta": {},
        }
    )
    await text_handlers_respond_phase6(ctx)
    assert ctx["action"] == "answer_question"
    reply = str(ctx["bot_reply_text"] or "").lower()
    assert "wa.me" not in reply
    assert ctx["bot_reply_text"] != wa_me_reply
    # Must not pretend the request was already recorded when the claim failed.
    assert "i’ve recorded" not in reply and "i've recorded" not in reply
    assert "reconfirm" in reply or "details" in reply


@pytest.mark.asyncio
async def test_ai_human_handover_without_user_request_uses_wa_me(wa_me_reply: str) -> None:
    ctx = _base_ctx(
        user_input_to_process="what are your hours?",
        gpt_response_data={
            "action": "human_handover",
            "bot_reply": "Connecting you to an agent.",
            "handover_degree": "high",
            "escalation_reason": "frustration_detected",
            "_flow_meta": {},
        },
    )
    await text_handlers_respond_phase6(ctx)
    assert ctx["action"] == "answer_question"
    assert "wa.me" in (ctx["bot_reply_text"] or "").lower()


@pytest.mark.asyncio
async def test_explicit_user_agent_request_keeps_human_handover(wa_me_reply: str) -> None:
    ctx = _base_ctx(
        user_input_to_process="I want to speak to a human agent please",
        gpt_response_data={
            "action": "human_handover",
            "bot_reply": "Connecting you now.",
            "handover_degree": "high",
            "escalation_reason": "customer_requested_human",
            "_flow_meta": {},
        },
    )
    await text_handlers_respond_phase6(ctx)
    assert ctx["action"] == "human_handover"


@pytest.mark.asyncio
async def test_human_handover_initial_ask_preserved(wa_me_reply: str) -> None:
    ctx = _base_ctx(
        user_input_to_process="this is frustrating",
        gpt_response_data={
            "action": "human_handover_initial_ask",
            "bot_reply": "Would you like me to connect you to the team?",
            "handover_degree": "medium",
            "_flow_meta": {},
        },
    )
    await text_handlers_respond_phase6(ctx)
    assert ctx["action"] == "human_handover_initial_ask"


def test_build_wa_me_handoff_guidance_uses_published_whatsapp(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.cm.structured_resolver import HandoffResolution

    monkeypatch.setattr(
        "services.cm.version_store.load_published_content",
        lambda tenant_id: (MagicMock(), {"handoff": {"contacts": [], "matrix": []}}),
    )
    monkeypatch.setattr(
        "services.cm.schemas.HandoffPolicy.model_validate",
        lambda payload: MagicMock(name="policy"),
    )
    monkeypatch.setattr(
        "services.cm.structured_resolver.resolve_handoff",
        lambda policy, **kwargs: HandoffResolution("whatsapp", "+96178847527", "Team", None),
    )

    text = build_wa_me_handoff_guidance(user_data={"tenant_id": "linas"}, language="en")
    assert "wa.me" in text.lower()
    assert "96178847527" in text
