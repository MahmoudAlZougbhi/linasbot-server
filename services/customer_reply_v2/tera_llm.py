"""Tera LLM calls — preserve requested low|medium effort (no silent none clamp)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from services.customer_reply_v2.flags import customer_ai_v10_runtime_enabled, customer_answer_model_name


def normalize_tera_effort(value: str | None) -> str:
    effort = str(value or "").strip().lower()
    if effort in {"low", "medium"}:
        return effort
    return "medium"


def _chat_tools_to_responses(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for tool in tools:
        fn = tool.get("function") if isinstance(tool, dict) else None
        if not isinstance(fn, dict):
            continue
        out.append(
            {
                "type": "function",
                "name": str(fn.get("name") or ""),
                "description": str(fn.get("description") or ""),
                "parameters": fn.get("parameters") or {"type": "object", "properties": {}},
            }
        )
    return out


def _wrap_chat_like(*, model: str, content: str, tool_calls: list[Any] | None, usage: Any) -> Any:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], model=model, usage=usage)


async def create_tera_completion(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None,
    channel: str,
    regeneration: bool,
    reasoning_effort: str,
) -> Any:
    from services.llm_core_service import build_chat_completion_kwargs, client
    from services.model_policy import emit_model_policy_trace, resolve_customer_social_policy

    if tools:
        from services.requests.capture_answer_loop import capture_tools_allowed

        if not capture_tools_allowed(tools):
            raise RuntimeError("Answer Tera must not receive retrieval tools")

    effort = normalize_tera_effort(reasoning_effort)
    policy = resolve_customer_social_policy(
        channel=channel,
        regeneration=regeneration,
        reasoning_effort=effort,
    )
    model = customer_answer_model_name()
    if model != policy.model:
        raise RuntimeError(f"customer_answer_model_misconfigured: answer model {model!r} != policy {policy.model!r}")

    v10 = customer_ai_v10_runtime_enabled()
    if v10 and tools:
        response = await _create_via_responses(
            client=client,
            model=model,
            messages=messages,
            tools=tools,
            effort=effort,
        )
        extra = {
            "role": "answer",
            "stage": "repair" if regeneration else "answer",
            "requested_reasoning_effort": effort,
            "effective_reasoning_effort": effort,
            "transport": "responses",
        }
        emit_model_policy_trace(policy, extra=extra)
        response._linas_requested_reasoning_effort = effort
        response._linas_effective_reasoning_effort = effort
        return response

    kwargs = build_chat_completion_kwargs(
        model=model,
        messages=[{"role": "user", "content": "placeholder"}],
        max_tokens=900,
        temperature=0.3,
        reasoning_effort=str(policy.reasoning_effort),
        has_function_tools=bool(tools),
    )
    kwargs["messages"] = messages
    kwargs["model"] = model
    if tools:
        kwargs["tools"] = tools
        kwargs["tool_choice"] = "auto"
    effective = str(kwargs.get("reasoning_effort") or policy.reasoning_effort)
    extra = {
        "role": "answer",
        "stage": "repair" if regeneration else "answer",
        "requested_reasoning_effort": str(policy.reasoning_effort),
        "effective_reasoning_effort": effective,
        "transport": "chat.completions",
    }
    emit_model_policy_trace(policy, extra=extra)
    response = await client.chat.completions.create(**kwargs)
    response._linas_requested_reasoning_effort = str(policy.reasoning_effort)
    response._linas_effective_reasoning_effort = effective
    return response


async def _create_via_responses(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    effort: str,
) -> Any:
    responses = getattr(client, "responses", None)
    if responses is None or not hasattr(responses, "create"):
        raise RuntimeError("tera_responses_api_unavailable: cannot keep Tera effort with tools")
    payload: dict[str, Any] = {
        "model": model,
        "input": messages,
        "tools": _chat_tools_to_responses(tools),
        "reasoning": {"effort": effort},
        "max_output_tokens": 2048,
    }
    raw = await responses.create(**payload)
    content = getattr(raw, "output_text", None) or ""
    tool_calls = _tool_calls_from_responses(raw)
    usage = getattr(raw, "usage", None)
    wrapped = _wrap_chat_like(
        model=getattr(raw, "model", None) or model, content=content, tool_calls=tool_calls, usage=usage
    )
    return wrapped


def _tool_calls_from_responses(raw: Any) -> list[Any] | None:
    output = getattr(raw, "output", None) or []
    calls: list[Any] = []
    for item in output:
        kind = str(getattr(item, "type", "") or "")
        if kind != "function_call":
            continue
        calls.append(
            SimpleNamespace(
                id=str(getattr(item, "call_id", None) or getattr(item, "id", "") or ""),
                function=SimpleNamespace(
                    name=str(getattr(item, "name", "") or ""),
                    arguments=str(getattr(item, "arguments", "") or "{}"),
                ),
            )
        )
    return calls or None
