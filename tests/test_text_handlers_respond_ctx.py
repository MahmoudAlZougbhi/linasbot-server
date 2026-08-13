"""Respond ctx bootstrap for worker / Meta DM paths."""

from __future__ import annotations

from unittest import mock

import pytest

from handlers.text_handlers_respond_ctx import bootstrap_process_respond_ctx
from handlers.text_handlers_respond_phase1 import text_handlers_respond_phase1


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
