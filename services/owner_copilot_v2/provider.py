"""Provider streaming helpers for Owner Copilot V2."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable
from typing import Any

from services.owner_copilot_v2.flags import owner_max_output_tokens, owner_model_name
from services.owner_copilot_v2.tool_schemas import OWNER_V2_TOOL_SCHEMAS

CancelCheck = Callable[[], bool]


async def sol_chat_completion(
    *,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    stream: bool = False,
) -> Any:
    from services.llm_core_service import build_chat_completion_kwargs, client

    model = owner_model_name()
    kwargs = build_chat_completion_kwargs(
        model=model,
        messages=[{"role": "user", "content": "placeholder"}],
        max_tokens=owner_max_output_tokens(),
        temperature=0.4,
    )
    kwargs["messages"] = messages
    if tools is not None:
        kwargs["tools"] = tools or OWNER_V2_TOOL_SCHEMAS
        kwargs["tool_choice"] = "auto"
    if stream:
        kwargs["stream"] = True
    return await client.chat.completions.create(**kwargs)


async def iter_sol_text_deltas(
    *,
    messages: list[dict[str, Any]],
    is_cancelled: CancelCheck | None = None,
) -> AsyncIterator[str]:
    """Yield real provider text deltas (not a post-hoc typing animation)."""
    stream = await sol_chat_completion(messages=messages, tools=None, stream=True)
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


async def collect_sol_text(
    *,
    messages: list[dict[str, Any]],
    is_cancelled: CancelCheck | None = None,
) -> tuple[str, bool]:
    parts: list[str] = []
    try:
        async for piece in iter_sol_text_deltas(messages=messages, is_cancelled=is_cancelled):
            parts.append(piece)
            if is_cancelled and is_cancelled():
                return "".join(parts), True
    except Exception:
        response = await sol_chat_completion(messages=messages, tools=None, stream=False)
        text = (response.choices[0].message.content or "").strip()
        return text, False
    return "".join(parts).strip(), False
