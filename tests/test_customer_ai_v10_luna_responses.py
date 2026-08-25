"""Luna+tools must keep effort=low via /v1/responses, never chat.completions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from services.customer_reply_v2.responses_transport import (
    chat_messages_to_responses_input,
    chat_tools_to_responses,
)
from services.model_policy import MODEL_CUSTOMER_LUNA

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "read_published_cm_items",
            "description": "read",
            "parameters": {"type": "object", "properties": {}},
        },
    }
]


def test_chat_tool_round_maps_to_responses_items():
    messages = [
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [
                {
                    "id": "c1",
                    "function": {
                        "name": "read_published_cm_items",
                        "arguments": '{"item_ids":["services:svc"]}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"ok":true}'},
    ]
    items = chat_messages_to_responses_input(messages)
    assert items[0] == {"role": "system", "content": "sys"}
    assert items[1] == {"role": "user", "content": "hi"}
    assert items[2]["type"] == "function_call"
    assert items[2]["call_id"] == "c1"
    assert items[2]["name"] == "read_published_cm_items"
    assert items[3] == {
        "type": "function_call_output",
        "call_id": "c1",
        "output": '{"ok":true}',
    }
    converted = chat_tools_to_responses(_TOOLS)
    assert converted[0]["type"] == "function"
    assert converted[0]["name"] == "read_published_cm_items"


@pytest.mark.asyncio
async def test_luna_default_llm_uses_responses_keeps_low_effort(v2_env, monkeypatch: pytest.MonkeyPatch):
    from services.customer_reply_v2.retrieval_luna import _default_llm, _luna_effective_effort

    captured: dict = {}

    async def _responses_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_text='{"evidence_status":"sufficient","recommended_tera_effort":"low"}',
            output=[],
            model=MODEL_CUSTOMER_LUNA,
            usage=SimpleNamespace(input_tokens=11, output_tokens=7, total_tokens=18),
        )

    async def _chat_create(**kwargs):
        raise AssertionError("V10 Luna+tools must use /v1/responses, not chat.completions")

    fake = SimpleNamespace(
        responses=SimpleNamespace(create=_responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=_chat_create)),
    )
    monkeypatch.setattr("services.llm_core_service.client", fake)

    response = await _default_llm(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "مرحبا"}],
        _TOOLS,
    )
    assert captured["model"] == MODEL_CUSTOMER_LUNA
    assert captured["reasoning"]["effort"] == "low"
    assert captured["tools"][0]["type"] == "function"
    assert captured["input"][0]["role"] == "system"
    assert response._linas_transport == "responses"
    assert response._linas_requested_reasoning_effort == "low"
    assert response._linas_effective_reasoning_effort == "low"
    assert _luna_effective_effort(MODEL_CUSTOMER_LUNA) == "low"
    assert response.usage.prompt_tokens == 11
    assert response.usage.completion_tokens == 7


def test_chat_multimodal_maps_to_responses_input_image() -> None:
    items = chat_messages_to_responses_input(
        [
            {"role": "system", "content": "sys"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": '{"comment":"🔥"}'},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,aaa"}},
                ],
            },
        ]
    )
    assert items[0] == {"role": "system", "content": "sys"}
    assert items[1]["role"] == "user"
    assert items[1]["content"][0] == {"type": "input_text", "text": '{"comment":"🔥"}'}
    assert items[1]["content"][1] == {
        "type": "input_image",
        "image_url": "data:image/jpeg;base64,aaa",
    }


@pytest.mark.asyncio
async def test_tera_comment_without_tools_uses_responses(v2_env, monkeypatch: pytest.MonkeyPatch):
    from services.customer_reply_v2.tera_llm import create_tera_completion
    from services.model_policy import MODEL_CUSTOMER_TERRA

    captured: dict = {}

    async def _responses_create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            output_text='{"reply_text":"ok","grounding_status":"grounded"}',
            output=[],
            model=MODEL_CUSTOMER_TERRA,
            usage=SimpleNamespace(input_tokens=9, output_tokens=4, total_tokens=13),
        )

    async def _chat_create(**kwargs):
        raise AssertionError("V10 Tera comments must use /v1/responses, not chat.completions")

    fake = SimpleNamespace(
        responses=SimpleNamespace(create=_responses_create),
        chat=SimpleNamespace(completions=SimpleNamespace(create=_chat_create)),
    )
    monkeypatch.setattr("services.llm_core_service.client", fake)

    response = await create_tera_completion(
        messages=[
            {"role": "system", "content": "sys"},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "hi"},
                    {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,aaa"}},
                ],
            },
        ],
        tools=None,
        channel="instagram_comment",
        regeneration=False,
        reasoning_effort="low",
    )
    assert captured["model"] == MODEL_CUSTOMER_TERRA
    assert captured["reasoning"]["effort"] == "low"
    assert "tools" not in captured
    assert captured["input"][1]["content"][1]["type"] == "input_image"
    assert response._linas_transport == "responses"
    assert response.choices[0].message.content.startswith("{")


@pytest.mark.asyncio
async def test_public_comment_does_not_post_model_unavailable_sentence(v2_env) -> None:
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment
    from tests.cm_test_helpers import publish_test_content
    from tests.customer_reply_ai_v2_helpers import _rich_sections

    await publish_test_content("t_no_canned", _rich_sections())
    out = await run_customer_reply_v2_comment(
        tenant_id="t_no_canned",
        comment_text="🔥",
        detected_language="en",
        response_language="en",
        channel="instagram_comment",
        scripted_retrieval=[{"final_plan": {"evidence_status": "sufficient", "selected_source_ids": []}}],
        fixture_answer={
            "reply_text": "",
            "grounding_status": "insufficient",
            "safe_failure_category": "model_unavailable",
        },
    )
    assert out.reply is None
    assert "temporarily unavailable" not in str(out.reply or "")
    assert "answer_model_unavailable" in (out.metadata.get("failed_rules") or [])


@pytest.mark.asyncio
async def test_luna_fail_closed_without_responses_api(v2_env, monkeypatch: pytest.MonkeyPatch):
    from services.customer_reply_v2.retrieval_luna import _default_llm

    async def _chat_create(**kwargs):
        raise AssertionError("must not silently fall back to chat.completions")

    fake = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=_chat_create)),
    )
    monkeypatch.setattr("services.llm_core_service.client", fake)
    with pytest.raises(RuntimeError, match="responses_api_unavailable"):
        await _default_llm([{"role": "user", "content": "hi"}], _TOOLS)


@pytest.mark.asyncio
async def test_luna_selected_ids_are_read_into_evidence(v2_env):
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna
    from tests.cm_test_helpers import publish_test_content
    from tests.customer_reply_ai_v2_helpers import _rich_sections

    await publish_test_content("t_hydrate", _rich_sections())
    result = await run_retrieval_luna(
        tenant_id="t_hydrate",
        message="hours",
        customer_profile={},
        scripted_tool_calls=[
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": ["knowledge:kn_hours"],
                    "recommended_tera_effort": "low",
                }
            }
        ],
    )
    bodies = [str(e.content or "") for e in result.evidence if e.source_id == "knowledge:kn_hours"]
    assert bodies
    assert any("open tomorrow" in body.lower() for body in bodies)
