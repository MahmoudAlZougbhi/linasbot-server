from __future__ import annotations

# services/llm_core_service.py
from typing import Any

from openai import AsyncOpenAI

import config

# تهيئة عميل OpenAI
client = AsyncOpenAI(api_key=config.OPENAI_API_KEY)


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
    # gpt-5-mini / gpt-5 / gpt-5-nano reject non-default temperature.
    if m.startswith("gpt-5") and not m.startswith("gpt-5.4"):
        return False
    return True


def build_chat_completion_kwargs(
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float | None = None,
) -> dict[str, Any]:
    """Build OpenAI chat.completions.create kwargs compatible with GPT-5 param rules."""
    kwargs: dict[str, Any] = {
        "model": model,
        "messages": messages,
    }
    if uses_max_completion_tokens(model):
        kwargs["max_completion_tokens"] = int(max_tokens)
    else:
        kwargs["max_tokens"] = int(max_tokens)

    if temperature is not None and temperature_supported(model):
        kwargs["temperature"] = float(temperature)
    return kwargs


async def create_chat_completion(
    *,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int,
    temperature: float | None = None,
) -> Any:
    """Thin wrapper so guest/owner paths share GPT-5-safe parameter shaping."""
    kwargs = build_chat_completion_kwargs(
        model=model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=temperature,
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
