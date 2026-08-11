"""Final OpenAI model-routing policy — verifies actual chat.completions payloads."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest

from services.llm_core_service import build_chat_completion_kwargs
from services.model_policy import (
    MODEL_CUSTOMER_TERRA,
    MODEL_OWNER_SOL,
    assert_customer_social_model,
    resolve_customer_social_policy,
    resolve_owner_policy,
    validate_model_policy_config,
)


def _assert_payload(kwargs: dict[str, Any], *, model: str, effort: str) -> None:
    assert kwargs["model"] == model
    assert kwargs.get("reasoning_effort") == effort
    assert "gpt-5.6" != model  # never generic alias
    assert model in {MODEL_OWNER_SOL, MODEL_CUSTOMER_TERRA}


@pytest.mark.parametrize(
    ("text", "effort"),
    [
        ("How does billing work in Linas AI?", "low"),
        ("What is available in AI Setup?", "high"),
        ("Please change the laser price to 50", "high"),
        ("Delete the downtown branch", "high"),
        ("Change the AI response style to warmer", "high"),
        ("Update the app UI design for the landing page", "high"),
        ("What is my FAQ quota and also publish the CM draft", "high"),
        ("Maybe update something in the prices section?", "high"),
        ("Ask about our FAQ answers", "high"),
        ("شو ساعات الدوام؟", "high"),
    ],
)
def test_owner_policy_effort_matrix(text: str, effort: str) -> None:
    decision = resolve_owner_policy(surface="owner_copilot", user_text=text)
    assert decision.model == MODEL_OWNER_SOL
    assert decision.reasoning_mode == "standard"
    assert decision.reasoning_effort == effort
    kwargs = build_chat_completion_kwargs(
        model=decision.model,
        messages=[{"role": "user", "content": "x"}],
        max_tokens=500,
        reasoning_effort=str(decision.reasoning_effort),
    )
    _assert_payload(kwargs, model=MODEL_OWNER_SOL, effort=effort)


def test_owner_continuation_keeps_effort() -> None:
    first = resolve_owner_policy(surface="owner_copilot", user_text="Delete the downtown branch")
    cont = resolve_owner_policy(prior=first)
    assert cont.model == MODEL_OWNER_SOL
    assert cont.reasoning_effort == "high"
    assert cont.surface == "owner_tool_continuation"


def test_owner_ui_mode_chat_low_work_high() -> None:
    """Mobile Chat|Work maps to Sol effort; UI displays 5.6 LIN (not Sol)."""
    chat = resolve_owner_policy(
        surface="owner_copilot",
        user_text="How does billing work in Linas AI?",
        owner_mode="chat",
    )
    assert chat.model == MODEL_OWNER_SOL
    assert chat.reasoning_effort == "low"
    assert chat.reason == "owner_mode_chat"

    cm_while_chat = resolve_owner_policy(
        surface="owner_copilot",
        user_text="Please change the laser price to 50",
        owner_mode="chat",
    )
    assert cm_while_chat.reasoning_effort == "high"
    assert cm_while_chat.reason == "cm_work_intent"

    work = resolve_owner_policy(
        surface="owner_copilot",
        user_text="How does billing work?",
        owner_mode="work",
    )
    assert work.model == MODEL_OWNER_SOL
    assert work.reasoning_effort == "high"
    assert work.reason == "owner_mode_work"

    confirm = resolve_owner_policy(
        surface="owner_copilot",
        confirm_tool="approve_cm_patch:abc",
        owner_mode="chat",
        force_high=True,
    )
    assert confirm.reasoning_effort == "high"


def test_owner_stream_route_suggests_work_for_high() -> None:
    from services.model_policy import owner_stream_route_payload

    high = resolve_owner_policy(surface="owner_copilot", user_text="Update FAQ answers")
    route = owner_stream_route_payload(high)
    assert route["reasoning_effort"] == "high"
    assert route["suggested_owner_mode"] == "work"

    low = resolve_owner_policy(
        surface="owner_copilot",
        user_text="How does billing work in Linas AI?",
        owner_mode="chat",
    )
    low_route = owner_stream_route_payload(low)
    assert low_route["reasoning_effort"] == "low"
    assert "suggested_owner_mode" not in low_route


@pytest.mark.parametrize(
    "channel",
    [
        "instagram_dm",
        "facebook_messenger",
        "instagram_comment",
        "facebook_comment",
    ],
)
def test_customer_social_terra_medium_payload(channel: str) -> None:
    decision = resolve_customer_social_policy(channel=channel)
    assert decision.model == MODEL_CUSTOMER_TERRA
    assert decision.reasoning_mode == "standard"
    assert decision.reasoning_effort == "medium"
    kwargs = build_chat_completion_kwargs(
        model=decision.model,
        messages=[{"role": "user", "content": "x"}],
        max_tokens=500,
        reasoning_effort=str(decision.reasoning_effort),
    )
    _assert_payload(kwargs, model=MODEL_CUSTOMER_TERRA, effort="medium")


def test_customer_retry_and_continuation_stay_terra_medium() -> None:
    retry = resolve_customer_social_policy(channel="instagram_dm", regeneration=True)
    cont = resolve_customer_social_policy(channel="facebook_messenger", continuation=True)
    for decision in (retry, cont):
        assert decision.model == MODEL_CUSTOMER_TERRA
        assert decision.reasoning_effort == "medium"
        kwargs = build_chat_completion_kwargs(
            model=decision.model,
            messages=[{"role": "user", "content": "x"}],
            max_tokens=400,
            reasoning_effort=str(decision.reasoning_effort),
        )
        _assert_payload(kwargs, model=MODEL_CUSTOMER_TERRA, effort="medium")


def test_assert_customer_social_rejects_luna_sol_legacy() -> None:
    for bad in ("gpt-5.6-luna", "gpt-5.6-sol", "gpt-5.5", "gpt-5.4-mini", "gpt-5.1", "gpt-4o"):
        with pytest.raises(RuntimeError, match="customer_social_model_violation"):
            assert_customer_social_model(bad)
    assert assert_customer_social_model(MODEL_CUSTOMER_TERRA) == MODEL_CUSTOMER_TERRA


def test_env_cannot_silently_override_customer_or_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_CUSTOMER_MODEL", "gpt-5.6-luna")
    with pytest.raises(RuntimeError, match="LINAS_MODEL_POLICY_INVALID"):
        validate_model_policy_config()
    monkeypatch.delenv("LINAS_CUSTOMER_MODEL", raising=False)
    monkeypatch.setenv("LINAS_OWNER_MODEL", "gpt-5.6-luna")
    with pytest.raises(RuntimeError, match="LINAS_MODEL_POLICY_INVALID"):
        validate_model_policy_config()
    monkeypatch.setenv("LINAS_OWNER_MODEL", MODEL_OWNER_SOL)
    monkeypatch.setenv("LINAS_CUSTOMER_MODEL", MODEL_CUSTOMER_TERRA)
    snap = validate_model_policy_config()
    assert snap["ok"] is True


@pytest.mark.asyncio
async def test_cm_answer_generation_openai_payload_is_terra_medium(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.cm import answer_generation as ag
    from services.cm.schemas import AnswerPacket

    captured: dict[str, Any] = {}

    async def _fake_create(**kwargs: Any) -> Any:
        captured.update(kwargs)
        msg = MagicMock()
        msg.content = "ok"
        choice = MagicMock()
        choice.message = msg
        usage = MagicMock()
        usage.prompt_tokens = 10
        usage.completion_tokens = 5
        resp = MagicMock()
        resp.choices = [choice]
        resp.usage = usage
        return resp

    monkeypatch.setattr(ag, "create_chat_completion", _fake_create)
    packet = AnswerPacket(
        tenant_id="t1",
        content_version_id="v1",
        detected_language="en",
        response_language="en",
    )
    result = await ag.generate_answer_with_usage("hi", packet)
    assert result.model == MODEL_CUSTOMER_TERRA
    assert captured["model"] == MODEL_CUSTOMER_TERRA
    assert captured["reasoning_effort"] == "medium"


@pytest.mark.asyncio
async def test_owner_provider_openai_payload_sol_effort(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.model_policy import resolve_owner_policy
    from services.owner_copilot_v2 import provider as prov

    captured: dict[str, Any] = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs: Any) -> Any:
                    captured.update(kwargs)
                    msg = MagicMock()
                    msg.content = "hello"
                    msg.tool_calls = None
                    choice = MagicMock()
                    choice.message = msg
                    resp = MagicMock()
                    resp.choices = [choice]
                    return resp

    monkeypatch.setattr("services.llm_core_service.client", _FakeClient)
    low = resolve_owner_policy(surface="owner_copilot", user_text="How does usage work?")
    await prov.sol_chat_completion(
        messages=[{"role": "user", "content": "How does usage work?"}],
        tools=None,
        stream=False,
        policy=low,
    )
    assert captured["model"] == MODEL_OWNER_SOL
    assert captured["reasoning_effort"] == "low"

    captured.clear()
    high = resolve_owner_policy(surface="owner_copilot", user_text="Publish my CM draft")
    await prov.sol_chat_completion(
        messages=[{"role": "user", "content": "Publish my CM draft"}],
        tools=None,
        stream=False,
        policy=high,
    )
    assert captured["model"] == MODEL_OWNER_SOL
    assert captured["reasoning_effort"] == "high"

    # Regression: Sol + function tools on chat.completions must force effort=none
    # (OpenAI 400: tools with reasoning_effort unsupported for gpt-5.6-sol).
    captured.clear()
    await prov.sol_chat_completion(
        messages=[{"role": "user", "content": "How does usage work?"}],
        tools=[{"type": "function", "function": {"name": "help", "parameters": {}}}],
        stream=False,
        policy=low,
    )
    assert captured["model"] == MODEL_OWNER_SOL
    assert captured["reasoning_effort"] == "none"
    assert captured.get("tools")
    assert captured.get("tool_choice") == "auto"


def test_sol_chat_completions_tools_force_none_effort() -> None:
    from services.llm_core_service import (
        build_chat_completion_kwargs,
        effective_chat_completions_reasoning_effort,
    )

    assert (
        effective_chat_completions_reasoning_effort(
            model=MODEL_OWNER_SOL,
            reasoning_effort="high",
            has_function_tools=True,
        )
        == "none"
    )
    assert (
        effective_chat_completions_reasoning_effort(
            model=MODEL_OWNER_SOL,
            reasoning_effort="low",
            has_function_tools=False,
        )
        == "low"
    )
    # Terra keeps medium even with tools on chat.completions.
    assert (
        effective_chat_completions_reasoning_effort(
            model=MODEL_CUSTOMER_TERRA,
            reasoning_effort="medium",
            has_function_tools=True,
        )
        == "medium"
    )
    kwargs = build_chat_completion_kwargs(
        model=MODEL_OWNER_SOL,
        messages=[{"role": "user", "content": "x"}],
        max_tokens=500,
        reasoning_effort="high",
        has_function_tools=True,
    )
    assert kwargs["reasoning_effort"] == "none"


@pytest.mark.asyncio
async def test_customer_v2_answer_payload_terra_medium(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_reply_v2 import answer_luna as al

    captured: dict[str, Any] = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs: Any) -> Any:
                    captured.update(kwargs)
                    msg = MagicMock()
                    msg.content = '{"reply_text":"hi","grounding_status":"grounded"}'
                    choice = MagicMock()
                    choice.message = msg
                    resp = MagicMock()
                    resp.choices = [choice]
                    resp.model = MODEL_CUSTOMER_TERRA
                    return resp

    monkeypatch.setattr("services.llm_core_service.client", _FakeClient)
    await al._default_llm([{"role": "user", "content": "{}"}])
    assert captured["model"] == MODEL_CUSTOMER_TERRA
    assert captured["reasoning_effort"] == "medium"


@pytest.mark.asyncio
async def test_customer_v2_retrieval_continuation_payload(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.customer_reply_v2 import retrieval_luna as rl

    captured: dict[str, Any] = {}

    class _FakeClient:
        class chat:
            class completions:
                @staticmethod
                async def create(**kwargs: Any) -> Any:
                    captured.update(kwargs)
                    msg = MagicMock()
                    msg.content = "{}"
                    msg.tool_calls = None
                    choice = MagicMock()
                    choice.message = msg
                    resp = MagicMock()
                    resp.choices = [choice]
                    resp.model = MODEL_CUSTOMER_TERRA
                    return resp

    monkeypatch.setattr("services.llm_core_service.client", _FakeClient)
    await rl._default_llm([{"role": "user", "content": "{}"}], tools=[{"type": "function"}])
    assert captured["model"] == MODEL_CUSTOMER_TERRA
    assert captured["reasoning_effort"] == "medium"


def test_model_router_and_provider_defaults_are_sol_terra(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in (
        "LINAS_MODEL_CUSTOMER_DM",
        "LINAS_MODEL_OWNER_CHAT",
        "LINAS_MODEL_SETUP",
        "LINAS_MODEL_CREATIVE",
        "LINAS_OWNER_HELP_MODEL",
        "LINAS_OWNER_CM_MODEL",
        "LINAS_CREATIVE_MODEL",
        "LINAS_CUSTOMER_HV_MODEL",
        "LINAS_CM_ANSWER_MODEL",
        "LINAS_CUSTOMER_MODEL",
        "LINAS_OWNER_MODEL",
    ):
        monkeypatch.delenv(key, raising=False)

    from services.cm.answer_generation import DEFAULT_CM_ANSWER_MODEL, cm_answer_model
    from services.customer_reply_v2.flags import customer_model_name
    from services.owner_ai_model_router import router_config
    from services.providers.base import provider_config

    cfg = provider_config()
    assert cfg["text"]["customer_dm"] == MODEL_CUSTOMER_TERRA
    assert cfg["text"]["owner_chat"] == MODEL_OWNER_SOL
    assert router_config()["customer_high_volume"]["model"] == MODEL_CUSTOMER_TERRA
    assert router_config()["owner_help"]["model"] == MODEL_OWNER_SOL
    assert DEFAULT_CM_ANSWER_MODEL == MODEL_CUSTOMER_TERRA
    assert cm_answer_model() == MODEL_CUSTOMER_TERRA
    assert customer_model_name() == MODEL_CUSTOMER_TERRA


def test_no_active_social_getter_returns_forbidden_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINAS_CUSTOMER_MODEL", "gpt-5.6-luna")
    monkeypatch.setenv("LINAS_CM_ANSWER_MODEL", "gpt-5.6-sol")
    from services.cm.answer_generation import cm_answer_model
    from services.customer_reply_v2.flags import customer_model_name

    # Policy hardcodes Terra; getters must not honor luna/sol env overrides.
    assert customer_model_name() == MODEL_CUSTOMER_TERRA
    assert cm_answer_model() == MODEL_CUSTOMER_TERRA
