"""Provider streaming helpers for Owner Copilot V2."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any, Literal

from services.model_policy import ModelPolicyDecision, emit_model_policy_trace, resolve_owner_policy
from services.owner_copilot_v2.flags import owner_max_output_tokens, owner_model_name

CancelCheck = Callable[[], bool]


@dataclass
class _FnDelta:
    name: str = ""
    arguments: str = ""


@dataclass
class AssembledToolCall:
    """OpenAI-shaped tool call assembled from streamed deltas."""

    id: str
    function: _FnDelta = field(default_factory=_FnDelta)


@dataclass
class ToolRoundResult:
    """Outcome of one streamed Sol round that may include tools."""

    content: str
    tool_calls: list[AssembledToolCall]


async def sol_chat_completion(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
    policy: ModelPolicyDecision | None = None,
) -> Any:
    from services.llm_core_service import build_chat_completion_kwargs, client
    from services.owner_copilot_v2.tool_schemas import OWNER_V2_TOOL_SCHEMAS

    decision = policy or resolve_owner_policy(surface="owner_copilot")
    model = decision.model or owner_model_name()
    # Every owner turn offers tools; Sol chat.completions forbids tools+low/high.
    # Keep policy effort for text-only (final answer) streams; clamp tool rounds to none.
    has_tools = tools is not None
    kwargs = build_chat_completion_kwargs(
        model=model,
        messages=[{"role": "user", "content": "placeholder"}],
        max_tokens=owner_max_output_tokens(),
        temperature=0.4,
        reasoning_effort=str(decision.reasoning_effort),
        has_function_tools=has_tools,
    )
    kwargs["messages"] = messages
    kwargs["model"] = model
    if has_tools:
        kwargs["tools"] = tools or OWNER_V2_TOOL_SCHEMAS
        kwargs["tool_choice"] = "auto"
    if stream:
        kwargs["stream"] = True
    emit_model_policy_trace(
        decision,
        extra={
            "stream": stream,
            "has_tools": has_tools,
            "chat_completions_effort": kwargs.get("reasoning_effort"),
        },
    )
    return await client.chat.completions.create(**kwargs)


async def iter_sol_text_deltas(
    *,
    messages: list[dict[str, Any]],
    is_cancelled: CancelCheck | None = None,
    policy: ModelPolicyDecision | None = None,
) -> AsyncIterator[str]:
    """Yield real provider text deltas (not a post-hoc typing animation)."""
    stream = await sol_chat_completion(messages=messages, tools=None, stream=True, policy=policy)
    async for event in stream:
        if is_cancelled and is_cancelled():
            return
        try:
            delta = event.choices[0].delta
            piece = getattr(delta, "content", None) or ""
        except Exception:
            piece = ""
        if piece:
            yield piece


async def iter_sol_tool_round(
    *,
    messages: list[dict[str, Any]],
    is_cancelled: CancelCheck | None = None,
    policy: ModelPolicyDecision | None = None,
) -> AsyncIterator[tuple[Literal["delta"], str] | tuple[Literal["result"], ToolRoundResult]]:
    """
    Stream one Sol round with tools enabled.

    Yields ("delta", text) for live token streaming when the model answers in text.
    Ends with ("result", ToolRoundResult) carrying full content + assembled tool_calls.
    """
    from services.owner_copilot_v2.tool_schemas import OWNER_V2_TOOL_SCHEMAS

    stream = await sol_chat_completion(
        messages=messages,
        tools=OWNER_V2_TOOL_SCHEMAS,
        stream=True,
        policy=policy,
    )
    text_parts: list[str] = []
    tool_acc: dict[int, AssembledToolCall] = {}

    async for event in stream:
        if is_cancelled and is_cancelled():
            break
        try:
            delta = event.choices[0].delta
        except Exception:
            continue
        piece = getattr(delta, "content", None) or ""
        if piece:
            text_parts.append(piece)
            yield ("delta", piece)
        for tc in getattr(delta, "tool_calls", None) or []:
            try:
                idx = int(getattr(tc, "index", 0) or 0)
            except Exception:
                idx = 0
            slot = tool_acc.get(idx)
            if slot is None:
                slot = AssembledToolCall(id=str(getattr(tc, "id", None) or f"call_{idx}"))
                tool_acc[idx] = slot
            tc_id = getattr(tc, "id", None)
            if tc_id:
                slot.id = str(tc_id)
            fn = getattr(tc, "function", None)
            if fn is not None:
                name = getattr(fn, "name", None)
                if name:
                    slot.function.name = str(name)
                args = getattr(fn, "arguments", None)
                if args:
                    slot.function.arguments += str(args)

    ordered = [tool_acc[i] for i in sorted(tool_acc)]
    yield (
        "result",
        ToolRoundResult(content="".join(text_parts).strip(), tool_calls=ordered),
    )


async def collect_sol_text(
    *,
    messages: list[dict[str, Any]],
    is_cancelled: CancelCheck | None = None,
    policy: ModelPolicyDecision | None = None,
) -> tuple[str, bool]:
    parts: list[str] = []
    try:
        async for piece in iter_sol_text_deltas(messages=messages, is_cancelled=is_cancelled, policy=policy):
            parts.append(piece)
            if is_cancelled and is_cancelled():
                return "".join(parts), True
    except Exception:
        response = await sol_chat_completion(messages=messages, tools=None, stream=False, policy=policy)
        text = (response.choices[0].message.content or "").strip()
        return text, False
    return "".join(parts).strip(), False
