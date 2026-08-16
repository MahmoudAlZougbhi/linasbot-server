"""OpenAI /v1/responses transport for GPT-5.6 models that reject tools+effort on chat.completions."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


def chat_tools_to_responses(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
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


def chat_messages_to_responses_input(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Map chat.completions messages (including tool rounds) to Responses input items."""
    items: list[dict[str, Any]] = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        role = str(raw.get("role") or "").strip()
        if role in {"system", "user"}:
            items.append({"role": role, "content": str(raw.get("content") or "")})
            continue
        if role == "assistant":
            tool_calls = raw.get("tool_calls") or []
            if tool_calls:
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    fn_raw = call.get("function")
                    fn = fn_raw if isinstance(fn_raw, dict) else {}
                    items.append(
                        {
                            "type": "function_call",
                            "call_id": str(call.get("id") or ""),
                            "name": str(fn.get("name") or ""),
                            "arguments": str(fn.get("arguments") or "{}"),
                        }
                    )
            elif raw.get("content"):
                items.append({"role": "assistant", "content": str(raw.get("content") or "")})
            continue
        if role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": str(raw.get("tool_call_id") or ""),
                    "output": str(raw.get("content") or ""),
                }
            )
    return items


def output_text_from_responses(raw: Any) -> str:
    text = str(getattr(raw, "output_text", None) or "")
    if text.strip():
        return text
    chunks: list[str] = []
    for item in getattr(raw, "output", None) or []:
        kind = str(getattr(item, "type", "") or "")
        if kind == "message":
            for part in getattr(item, "content", None) or []:
                ptype = str(getattr(part, "type", "") or "")
                if ptype in {"output_text", "text"}:
                    chunks.append(str(getattr(part, "text", "") or ""))
        elif kind in {"output_text", "text"}:
            chunks.append(str(getattr(item, "text", "") or ""))
    return "".join(chunks)


def wrap_chat_like(*, model: str, content: str, tool_calls: list[Any] | None, usage: Any) -> Any:
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    choice = SimpleNamespace(message=message)
    return SimpleNamespace(choices=[choice], model=model, usage=_normalize_usage(usage))


def _normalize_usage(usage: Any) -> Any:
    if usage is None:
        return None
    prompt = getattr(usage, "prompt_tokens", None)
    if prompt is None:
        prompt = getattr(usage, "input_tokens", None)
    completion = getattr(usage, "completion_tokens", None)
    if completion is None:
        completion = getattr(usage, "output_tokens", None)
    total = getattr(usage, "total_tokens", None)
    return SimpleNamespace(
        prompt_tokens=prompt,
        completion_tokens=completion,
        total_tokens=total,
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )


def tool_calls_from_responses(raw: Any) -> list[Any] | None:
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


async def create_via_responses(
    *,
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    effort: str,
    max_output_tokens: int = 2048,
) -> Any:
    responses = getattr(client, "responses", None)
    if responses is None or not hasattr(responses, "create"):
        raise RuntimeError("responses_api_unavailable: cannot keep reasoning_effort with function tools")
    payload: dict[str, Any] = {
        "model": model,
        "input": chat_messages_to_responses_input(messages),
        "tools": chat_tools_to_responses(tools),
        "reasoning": {"effort": effort},
        "max_output_tokens": int(max_output_tokens),
    }
    raw = await responses.create(**payload)
    content = output_text_from_responses(raw)
    wrapped = wrap_chat_like(
        model=getattr(raw, "model", None) or model,
        content=content,
        tool_calls=tool_calls_from_responses(raw),
        usage=getattr(raw, "usage", None),
    )
    wrapped._linas_requested_reasoning_effort = effort
    wrapped._linas_effective_reasoning_effort = effort
    wrapped._linas_transport = "responses"
    return wrapped
