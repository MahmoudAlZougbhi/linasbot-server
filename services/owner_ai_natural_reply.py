"""Natural-language replies for owner help / unmatched questions (no tools)."""

from __future__ import annotations

import json
import os
from typing import Any

DEFAULT_OWNER_MODEL = "gpt-5.6-sol"


class OwnerAIModelError(RuntimeError):
    """Raised when the owner conversational model fails. No canned sales fallback."""


def owner_help_model_name() -> str:
    """Legacy helper path — always Sol from central model policy."""
    from services.model_policy import owner_model_id

    return owner_model_id()


async def generate_owner_conversational_reply(
    *,
    user_text: str,
    context: dict[str, Any],
    help_data: dict[str, Any] | None = None,
) -> str:
    """LLM reply for help / unmatched intents. Tools stay on the orchestrator path."""
    text = (user_text or "").strip()
    if not text:
        raise OwnerAIModelError("empty_owner_question")

    reply_lang = str(context.get("reply_language") or "en")
    system = str(context.get("system_prompt") or "You are Linas AI System Copilot.")
    knowledge = str(context.get("knowledge_block") or "")
    summary = context.get("conversation_summary")
    account = context.get("account_summary") or {}

    system_parts = [
        system,
        "For this turn: answer naturally and specifically. Do not repeat a generic pitch.",
        "Keep the warm friendly voice with tasteful emojis from the system prompt; do not get clownish.",
        "Do not claim you ran tools or changed CM/integrations unless the user already confirmed a tool result.",
        f"Reply language hint: {reply_lang}.",
        f"Account snapshot (compact): {json.dumps(account, ensure_ascii=False, default=str)[:1200]}",
    ]
    if knowledge:
        system_parts.append(knowledge)
    if help_data:
        system_parts.append(
            "Targeted help payload (use as facts, do not dump raw JSON): "
            + json.dumps(help_data, ensure_ascii=False, default=str)[:2500]
        )
    if summary:
        system_parts.append(str(summary))

    messages: list[dict[str, str]] = [{"role": "system", "content": "\n".join(system_parts)}]
    for m in context.get("recent_messages") or []:
        role = str(m.get("role") or "").strip().lower()
        content = str(m.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": text})

    from services.model_policy import emit_model_policy_trace, resolve_owner_policy

    policy = resolve_owner_policy(surface="owner_chat", user_text=text, intent="help")
    model = owner_help_model_name()
    try:
        from services.llm_core_service import create_chat_completion, sanitize_llm_error

        emit_model_policy_trace(policy)
        response = await create_chat_completion(
            model=model,
            messages=messages,
            max_tokens=int(os.getenv("LINAS_OWNER_MAX_OUTPUT_TOKENS") or "1200"),
            temperature=0.65,
            reasoning_effort=str(policy.reasoning_effort),
        )
    except Exception as exc:  # noqa: BLE001
        raise OwnerAIModelError(f"owner_llm_unavailable:{type(exc).__name__}:{sanitize_llm_error(exc)}") from exc

    try:
        reply = (response.choices[0].message.content or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise OwnerAIModelError(f"owner_llm_bad_response:{type(exc).__name__}") from exc

    if not reply:
        raise OwnerAIModelError("owner_llm_empty_reply")
    return reply
