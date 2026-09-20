"""Sol names Owner Copilot chats. Never copy the owner's first message as the title."""

from __future__ import annotations

import re
from typing import Any

from services.owner_copilot.chat_store import (
    is_default_conversation_title,
    owner_chat_store,
)

TITLE_MAX_LEN = 48

_TITLE_SYSTEM = (
    "You name one Owner Copilot chat for the side menu. "
    "Return only the title: 2 to 6 words, same language as the owner. "
    "No quotes, no trailing punctuation, no emoji unless the owner used one. "
    "Name the topic. Do not copy the owner's message verbatim."
)


def _collapse(text: str) -> str:
    return " ".join(str(text or "").replace("\r", "\n").split())


def sanitize_sol_chat_title(raw: str, *, user_text: str = "") -> str | None:
    """Keep a short Sol-authored label; reject empties and verbatim owner copies."""
    cleaned = _collapse(raw).strip(" \t\"'`“”‘’")
    cleaned = re.sub(r"[.!?]+$", "", cleaned).strip()
    if not cleaned or is_default_conversation_title(cleaned):
        return None
    if len(cleaned) > TITLE_MAX_LEN:
        cleaned = cleaned[:TITLE_MAX_LEN].rstrip()
    owner = _collapse(user_text)
    if owner and cleaned.casefold() == owner.casefold():
        return None
    if owner and owner.casefold().startswith(cleaned.casefold()) and len(cleaned) >= min(len(owner), 24):
        return None
    return cleaned or None


async def propose_sol_chat_title(*, user_text: str, reply_text: str, language: str | None = None) -> str | None:
    """Ask Sol for a side-menu title. Fail soft — leave New chat if the model is unavailable."""
    owner = _collapse(user_text)
    reply = _collapse(reply_text)[:400]
    if not owner and not reply:
        return None
    lang = (language or "").strip() or "the owner's language"
    try:
        from services.brain.llm_core_service import create_chat_completion
        from services.owner_copilot.flags import owner_model_name

        response = await create_chat_completion(
            model=owner_model_name(),
            messages=[
                {"role": "system", "content": _TITLE_SYSTEM},
                {
                    "role": "user",
                    "content": (
                        f"Language: {lang}\nOwner: {owner or '(no text)'}\nLinas: {reply or '(no reply yet)'}\nTitle:"
                    ),
                },
            ],
            max_tokens=64,
            reasoning_effort="low",
        )
        raw = str(response.choices[0].message.content or "")
    except Exception:
        return None
    return sanitize_sol_chat_title(raw, user_text=owner)


async def maybe_assign_sol_title(
    *,
    tenant_id: str,
    user_id: str,
    conversation_id: str,
    user_text: str,
    reply_text: str,
    language: str | None = None,
) -> str | None:
    """Persist a Sol title once while the conversation is still on the default name."""
    conv = owner_chat_store.get_conversation(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
    )
    if conv is None or not is_default_conversation_title(conv.title):
        return None
    user_turns = sum(1 for m in (conv.messages or []) if str(getattr(m, "role", "") or "") == "user")
    if user_turns > 1:
        return None
    proposed = await propose_sol_chat_title(
        user_text=user_text,
        reply_text=reply_text,
        language=language,
    )
    if not proposed:
        return None
    ok = owner_chat_store.rename(
        tenant_id=tenant_id,
        user_id=user_id,
        conversation_id=conversation_id,
        title=proposed,
    )
    return proposed if ok else None


def sse_title_if_named(title: str | None) -> dict[str, Any] | None:
    """Only push title_updated for a real name, not New chat."""
    if not title or is_default_conversation_title(title):
        return None
    return {"title": title}


__all__ = [
    "TITLE_MAX_LEN",
    "maybe_assign_sol_title",
    "propose_sol_chat_title",
    "sanitize_sol_chat_title",
    "sse_title_if_named",
]
