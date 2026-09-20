"""Optional short Terra ack before retrieve/tools, then the evidence-only final.

Flag ``CUSTOMER_DM_ACK_THEN_REPLY`` defaults on. Ack never invents prices,
hours, or product facts. Failure after ack stays silent (Terra fail path).
One ack per flushed burst — this module is invoked once per agentic turn.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any

from services.brain.contracts.turn import CustomerTurn
from services.brain.flags import env_flag

_EARLY_OUTBOUND: contextvars.ContextVar[Callable[[str], Awaitable[Any]] | None] = contextvars.ContextVar(
    "customer_dm_early_outbound",
    default=None,
)

_ACK_MAX_CHARS = 80
_ACK_SYSTEM = (
    "Write one short waiting line while you look up the customer's request. "
    "No prices, hours, product names, clinic facts, or a promised answer. "
    "No essay. One sentence, under twelve words. Match the customer's language."
)


def ack_then_reply_enabled(channel: str = "") -> bool:
    if not env_flag("CUSTOMER_DM_ACK_THEN_REPLY", default=True):
        return False
    allow = (os.getenv("CUSTOMER_DM_ACK_CHANNELS") or "").strip().lower()
    if not allow:
        return True
    ch = (channel or "").strip().lower()
    tokens = {part.strip() for part in allow.split(",") if part.strip()}
    return ch in tokens or any(token in ch for token in tokens)


def ack_line_is_safe(text: str) -> bool:
    line = " ".join(str(text or "").split())
    if not line or len(line) > _ACK_MAX_CHARS:
        return False
    if any(ch.isdigit() for ch in line):
        return False
    from services.brain.outbound_safety import looks_like_instruction_text

    return not looks_like_instruction_text(line)


@contextlib.asynccontextmanager
async def bind_customer_ack_sender(
    *,
    user_id: str,
    user_data: dict[str, Any],
    send_message_func: Callable[..., Awaitable[Any]],
) -> AsyncIterator[None]:
    async def _send(text: str) -> Any:
        user_data["_dm_ack_in_flight"] = True
        try:
            return await send_message_func(user_id, text)
        finally:
            user_data.pop("_dm_ack_in_flight", None)

    token = _EARLY_OUTBOUND.set(_send)
    try:
        yield
    finally:
        _EARLY_OUTBOUND.reset(token)


async def emit_bound_ack(text: str) -> bool:
    sender = _EARLY_OUTBOUND.get()
    if sender is None or not ack_line_is_safe(text):
        return False
    await sender(text)
    return True


async def generate_ack_line(turn: CustomerTurn, *, message: str) -> str:
    from services.brain.generate.reply import openai_configured
    from services.brain.llm_core_service import create_chat_completion
    from services.brain.providers.config import answer_model

    if not openai_configured():
        return ""
    lang = str((turn.extra or {}).get("response_language") or "").strip()
    cue = " ".join(str(message or "").split())[:180]
    user = f"Language code: {lang or 'customer'}. Inbound (language cue only, not facts): {cue}"
    try:
        response = await create_chat_completion(
            model=answer_model(),
            messages=[
                {"role": "system", "content": _ACK_SYSTEM},
                {"role": "user", "content": user},
            ],
            max_tokens=220,
        )
        return str(response.choices[0].message.content or "").strip()
    except Exception:
        return ""


async def maybe_send_heavy_turn_ack(turn: CustomerTurn, *, message: str, channel: str) -> str:
    extra = turn.extra if isinstance(turn.extra, dict) else {}
    if extra.get("_dm_ack_sent"):
        return ""
    if not ack_then_reply_enabled(channel):
        return ""
    if _EARLY_OUTBOUND.get() is None:
        return ""
    line = ack_line_is_safe(str(extra.get("_ack_fixture") or "")) and str(extra.get("_ack_fixture") or "")
    if not line:
        generated = await generate_ack_line(turn, message=message)
        line = generated if ack_line_is_safe(generated) else ""
    if not line:
        return ""
    sent = await emit_bound_ack(line)
    if not sent:
        return ""
    extra["_dm_ack_sent"] = True
    extra["ack_text"] = line
    extra["ack_then_reply"] = True
    turn.extra = extra
    return line
