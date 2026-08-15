"""Respond ctx bootstrap for worker / Meta DM paths."""

from __future__ import annotations

from unittest import mock

import pytest

from handlers.text_handlers_respond_ctx import bootstrap_process_respond_ctx
from handlers.text_handlers_respond_phase1 import text_handlers_respond_phase1
from handlers.text_handlers_respond_phase5 import text_handlers_respond_phase5


def test_bootstrap_injects_language_detection_service() -> None:
    ctx: dict = {}
    bootstrap_process_respond_ctx(ctx)
    assert ctx.get("language_detection_service") is not None
    assert callable(ctx.get("get_firestore_db"))
    assert callable(ctx.get("log_interaction"))


def test_bootstrap_injects_cm_and_gpt_runtime_deps() -> None:
    ctx: dict = {}
    bootstrap_process_respond_ctx(ctx)
    assert callable(ctx.get("_handle_published_cm_runtime"))
    assert callable(ctx.get("get_bot_chat_response"))
    assert callable(ctx.get("get_gender_from_message"))
    assert callable(ctx.get("router_route"))


def test_bootstrap_is_idempotent() -> None:
    ctx: dict = {}
    bootstrap_process_respond_ctx(ctx)
    first = ctx["language_detection_service"]
    bootstrap_process_respond_ctx(ctx)
    assert ctx["language_detection_service"] is first


@pytest.mark.asyncio
async def test_worker_entry_phase1_uses_bootstrap_language_service() -> None:
    """Regression: Redis worker path must not crash on missing language_detection_service."""
    ctx: dict = {
        "user_id": "facebook:worker-bootstrap-test",
        "user_name": "Test",
        "user_input_to_process": "Hello",
        "user_data": {
            "user_preferred_lang": "en",
            "current_conversation_id": None,
            "awaiting_name_input": False,
            "channel": "facebook",
            "tenant_id": "linas",
        },
        "send_message_func": mock.AsyncMock(),
        "send_action_func": mock.AsyncMock(),
        "user_image_base64": None,
        "user_image_format": "jpeg",
    }
    bootstrap_process_respond_ctx(ctx)

    class _LangSvc:
        def detect_language(self, **kwargs: object) -> dict[str, str]:
            return {
                "detected_language": "en",
                "response_language": "en",
            }

    ctx["language_detection_service"] = _LangSvc()

    with mock.patch(
        "services.cm.language_policy.resolve_customer_response_language",
        return_value="en",
    ):
        result = await text_handlers_respond_phase1(ctx)

    assert result is None
    assert ctx.get("language_detection_service") is not None
    assert ctx.get("response_language") == "en"


@pytest.mark.asyncio
async def test_gender_ack_then_answer_have_distinct_task_local_semantic_purposes() -> None:
    import config
    from services.meta_outbound_attempts import current_meta_outbound_send_purpose

    user_id = "facebook:semantic-gender"
    observed: list[str] = []

    async def send(*_args: object, **_kwargs: object) -> None:
        observed.append(current_meta_outbound_send_purpose())

    async def noop(*_args: object, **_kwargs: object) -> None:
        return None

    class _LocalQa:
        async def find_match_with_tier(self, *_args: object, **_kwargs: object) -> dict[str, object]:
            return {
                "match_score": 1.0,
                "tier": "exact",
                "qa_pair": {"answer": "answer", "question": "question", "language": "ar"},
                "matched_language": "ar",
            }

    config.user_greeting_stage[user_id] = 1
    ctx: dict[str, object] = {
        "_apply_turn_by_turn_policy": lambda _action, value, _language: value,
        "_build_arabic_respectful_address": lambda _gender, _name: "صديقي",
        "_is_price_intent": lambda _query: False,
        "_resume_original_question": False,
        "ai_primary_mode": False,
        "current_conversation_id": "conv-semantic-gender",
        "current_gender": "male",
        "current_preferred_lang": "ar",
        "detect_reschedule_intent": lambda _query: False,
        "get_dynamic_message": lambda *_args: "fallback",
        "gpt_response_data": None,
        "initial_user_query_to_process_original": "original question",
        "is_initial_message_for_gpt": True,
        "local_qa_service": _LocalQa(),
        "log_interaction": lambda *_args, **_kwargs: None,
        "query_pre_set_from_booking_confirmation": False,
        "query_to_send_to_gpt": "",
        "save_conversation_message_to_firestore": noop,
        "save_for_training_conversation_log": lambda *_args, **_kwargs: None,
        "send_message_func": send,
        "update_dashboard_metric_in_firestore": noop,
        "user_data": {
            "initial_user_query_to_process": "original question",
            "phone_number": f"room:{user_id}",
        },
        "user_id": user_id,
        "user_input_to_process": "male",
        "user_name": "Test User",
    }
    try:
        result = await text_handlers_respond_phase5(ctx)
    finally:
        config.user_greeting_stage.pop(user_id, None)

    assert result == "_PHASE_HALT"
    assert observed == ["gender_ack", "primary_reply"]
    assert current_meta_outbound_send_purpose() == "primary_reply"
