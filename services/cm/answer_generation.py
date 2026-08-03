"""Minimal "large AI" caller for the published CM runtime pipeline (plan §12 step 14).

The :class:`~services.cm.schemas.AnswerPacket` is a self-contained, grounded context bundle
(identity, style, facts, chunks, platform rules). This module turns it into a single OpenAI
chat completion — deliberately NOT the legacy ``get_bot_chat_response`` orchestration (booking
FSM/CRM/tool-calling), which is out of scope for the CM content-answer runtime. Callers that
need booking/CRM behavior should keep using the legacy path (``CM_RUNTIME_MODE=legacy``, the
default) until a future cutover phase.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from services.cm.schemas import AnswerPacket
from services.llm_core_service import client

_MODEL = "gpt-4o-mini"


def _build_system_prompt(packet: AnswerPacket) -> str:
    lines: list[str] = []
    identity = packet.identity
    lines.append(f"You are {identity.assistant_name}, the AI assistant for {identity.clinic_name}.")
    if identity.identity_summary:
        lines.append(identity.identity_summary)
    if identity.advanced_instructions:
        lines.append(identity.advanced_instructions)

    style = packet.style
    if style.tone or style.formality:
        lines.append(f"Tone: {style.tone or 'n/a'}. Formality: {style.formality or 'n/a'}.")
    if style.do_list:
        lines.append("Do: " + "; ".join(style.do_list))
    if style.dont_list:
        lines.append("Don't: " + "; ".join(style.dont_list))
    if style.style_body:
        lines.append(style.style_body)

    lines.append("PLATFORM RULES (never break these):")
    for rule in packet.platform_rules:
        lines.append(f"- {rule}")

    if packet.facts:
        lines.append("KNOWN FACTS (the only business facts you may state):")
        for fact in packet.facts:
            lines.append(f"- [{fact.kind}] {fact.value} (source: {fact.source_id})")
    else:
        lines.append("KNOWN FACTS: none provided — do not invent any business fact.")

    if packet.chunks:
        lines.append("REFERENCE CONTENT (for context, paraphrase, do not contradict):")
        for chunk in packet.chunks:
            lines.append(f"- ({chunk.source_id}) {chunk.text}")

    if packet.history_summary:
        lines.append(f"Conversation so far: {packet.history_summary}")

    lines.append(f"Respond ONLY in language code '{packet.response_language}'.")
    return "\n".join(lines)


async def generate_answer(message: str, packet: AnswerPacket) -> str:
    """Call the LLM once with the packet as grounding context. No tool calls, no side effects."""
    system_prompt = _build_system_prompt(packet)
    response = await client.chat.completions.create(
        model=_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        temperature=0.3,
    )
    return (response.choices[0].message.content or "").strip()


def make_regenerate_fn(message: str, packet: AnswerPacket) -> Callable[[str, list[str]], Awaitable[str]]:
    """Build a bound ``regenerate_fn`` for :func:`services.cm.runtime_pipeline.finalize_response`."""

    async def _regenerate(previous_text: str, failed_rules: list[str]) -> str:
        constraint = (
            "Your previous answer violated these rules: "
            + ", ".join(failed_rules)
            + ". Rewrite the answer, obeying every platform rule and only stating facts from KNOWN FACTS."
        )
        system_prompt = _build_system_prompt(packet) + "\n" + constraint
        response = await client.chat.completions.create(
            model=_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
                {"role": "assistant", "content": previous_text},
                {"role": "user", "content": constraint},
            ],
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()

    return _regenerate
