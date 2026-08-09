from __future__ import annotations

# services/llm_core_service.py
from typing import Any

from openai import AsyncOpenAI

import config

# تهيئة عميل OpenAI
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)

# Reasoning models burn invisible tokens inside max_completion_tokens; too-low caps
# return HTTP 200 with empty message content (seen on prod as guest_llm_empty_reply).
_REASONING_MIN_COMPLETION_TOKENS = 2048


def _model_family(model: str) -> str:
    return (model or "").strip().lower()


def uses_max_completion_tokens(model: str) -> bool:
    """GPT-5 / o-series chat models reject legacy max_tokens."""
    m = _model_family(model)
    return m.startswith("gpt-5") or m.startswith(("o1", "o3", "o4"))


def temperature_supported(model: str) -> bool:
    """Some GPT-5 family models only allow the default temperature (1)."""
    m = _model_family(model)
    if m.startswith(("o1", "o3", "o4")):
        return False
    # gpt-5-mini / gpt-5 / gpt-5.6-sol reject non-default temperature.
    if m.startswith("gpt-5") and not m.startswith("gpt-5.4"):
        return False
    return True


def reasoning_effort_for_model(model: str) -> str | None:
    """Legacy heuristic when callers do not pass an explicit policy effort.

    Prefer :func:`services.model_policy.resolve_*` + explicit ``reasoning_effort``
    on owner/customer social paths. Guest/other non-policy callers may still use this.
    """
    m = _model_family(model)
    if m.startswith(("o1", "o3", "o4")):
        return "low"
    if "terra" in m:
        return "medium"
    if "luna" in m:
        return "none"
    if "sol" in m:
        return "low"
    if m.startswith("gpt-5") and not m.startswith("gpt-5.4"):
        return "low"
    return None


def build_chat_completion_kwargs(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
) -> dict[str, Any]:
    """Build OpenAI chat.completions.create kwargs compatible with GPT-5 param rules.

    When ``reasoning_effort`` is provided (model policy), it is written into the
    payload as-is. Otherwise a model-name heuristic is used for non-policy callers.
    """
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if uses_max_completion_tokens(model):
        # Floor budget so reasoning tokens don't consume the entire cap before text.
        budget = max(int(max_tokens), _REASONING_MIN_COMPLETION_TOKENS)
        kwargs["max_completion_tokens"] = budget
        effort = reasoning_effort if reasoning_effort is not None else reasoning_effort_for_model(model)
        if effort:
            kwargs["reasoning_effort"] = effort
    else:
        kwargs["max_tokens"] = int(max_tokens)

    if temperature is not None and temperature_supported(model):
        kwargs["temperature"] = float(temperature)
    return kwargs


async def create_chat_completion(
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float | None = None,
    reasoning_effort: str | None = None,
) -> Any:
    """Thin wrapper so guest/owner paths share GPT-5-safe parameter shaping."""
    kwargs = build_chat_completion_kwargs(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
        reasoning_effort=reasoning_effort,
    )
    return await client.chat.completions.create(**kwargs)


def sanitize_llm_error(exc: BaseException, *, limit: int = 220) -> str:
    """Surface provider errors for ops without dumping secrets."""
    text = " ".join(str(exc).split())
    lowered = text.lower()
    for needle in ("sk-", "api_key", "authorization", "bearer "):
        if needle in lowered:
            return type(exc).__name__
    return text[:limit]
