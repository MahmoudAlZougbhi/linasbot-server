"""Minimal "large AI" caller for the published CM runtime pipeline (plan §12 step 14).

The :class:`~services.cm.schemas.AnswerPacket` is a self-contained, grounded context bundle
(identity, style, facts, chunks, platform rules). This module turns it into a single OpenAI
chat completion — deliberately NOT the legacy ``get_bot_chat_response`` orchestration (booking
FSM/CRM/tool-calling), which is out of scope for the CM content-answer runtime. Callers that
need booking/CRM behavior should keep using the legacy path (``CM_RUNTIME_MODE=legacy``, the
default) until a future cutover phase.
"""

from __future__ import annotations

import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from services.cm.schemas import AnswerPacket
from services.llm_core_service import create_chat_completion
from services.model_pricing import COST_BASIS_TOKEN_RATES, compute_cost_from_usage

# Customer-facing CM DMs/comments — OpenAI API id gpt-5.6-luna (no weak fallback).
DEFAULT_CM_ANSWER_MODEL = "gpt-5.6-luna"


def cm_answer_model() -> str:
    return (
        os.getenv("LINAS_CM_ANSWER_MODEL") or os.getenv("LINAS_MODEL_CUSTOMER_DM") or DEFAULT_CM_ANSWER_MODEL
    ).strip() or DEFAULT_CM_ANSWER_MODEL


@dataclass
class AnswerGenerationResult:
    text: str
    model: str = DEFAULT_CM_ANSWER_MODEL
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    cost_usd: float | None = None
    input_cost_usd: float | None = None
    output_cost_usd: float | None = None
    cost_status: str = "unavailable"
    cost_basis: str | None = None
    call_count: int = 1


@dataclass
class UsageAccumulator:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    models: list[str] = field(default_factory=list)

    def add_from_response(self, response: Any, model: str) -> None:
        usage = getattr(response, "usage", None)
        pt = int(getattr(usage, "prompt_tokens", 0) or 0) if usage else 0
        ct = int(getattr(usage, "completion_tokens", 0) or 0) if usage else 0
        self.prompt_tokens += pt
        self.completion_tokens += ct
        self.calls += 1
        self.models.append(model)

    def to_result(self, text: str, model: str) -> AnswerGenerationResult:
        if self.calls == 0 or (self.prompt_tokens == 0 and self.completion_tokens == 0):
            return AnswerGenerationResult(text=text, model=model, cost_status="unavailable", call_count=self.calls)
        costs = compute_cost_from_usage(model, self.prompt_tokens, self.completion_tokens)
        return AnswerGenerationResult(
            text=text,
            model=model,
            prompt_tokens=self.prompt_tokens,
            completion_tokens=self.completion_tokens,
            total_tokens=self.prompt_tokens + self.completion_tokens,
            cost_usd=costs["cost_usd"],
            input_cost_usd=costs["input_cost_usd"],
            output_cost_usd=costs["output_cost_usd"],
            cost_status="estimated",
            cost_basis=COST_BASIS_TOKEN_RATES,
            call_count=self.calls,
        )


def _build_system_prompt(packet: AnswerPacket) -> str:
    lines: list[str] = []
    identity = packet.identity
    assistant = (identity.assistant_name or "").strip() or "the business assistant"
    business = (identity.clinic_name or "").strip() or "this business"
    lines.append(f"You are {assistant}, the AI assistant for {business}.")
    lines.append(
        "Use only the identity and facts in this packet. "
        "Do not invent another brand, clinic, city, doctor, or phone number."
    )
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
    """Call the LLM once with the packet as grounding context. No tool calls, no side effects.

    Returns reply text only (backward compatible). Prefer :func:`generate_answer_with_usage`
    when Interaction Logs need token/cost fields.
    """
    result = await generate_answer_with_usage(message, packet)
    return result.text


async def generate_answer_with_usage(message: str, packet: AnswerPacket) -> AnswerGenerationResult:
    """Call the LLM once and return text + real OpenAI usage tokens / estimated USD cost."""
    model = cm_answer_model()
    system_prompt = _build_system_prompt(packet)
    response = await create_chat_completion(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": message},
        ],
        max_tokens=800,
        temperature=0.3,
    )
    text = (response.choices[0].message.content or "").strip()
    acc = UsageAccumulator()
    acc.add_from_response(response, model)
    return acc.to_result(text, model)


def make_regenerate_fn(message: str, packet: AnswerPacket) -> Callable[[str, list[str]], Awaitable[str]]:
    """Build a bound ``regenerate_fn`` for :func:`services.cm.runtime_pipeline.finalize_response`."""

    async def _regenerate(previous_text: str, failed_rules: list[str]) -> str:
        model = cm_answer_model()
        constraint = (
            "Your previous answer violated these rules: "
            + ", ".join(failed_rules)
            + ". Rewrite the answer, obeying every platform rule and only stating facts from KNOWN FACTS."
        )
        system_prompt = _build_system_prompt(packet) + "\n" + constraint
        response = await create_chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
                {"role": "assistant", "content": previous_text},
                {"role": "user", "content": constraint},
            ],
            max_tokens=800,
            temperature=0.2,
        )
        return (response.choices[0].message.content or "").strip()

    return _regenerate


def make_regenerate_fn_with_usage(
    message: str,
    packet: AnswerPacket,
    usage_acc: UsageAccumulator,
) -> Callable[[str, list[str]], Awaitable[str]]:
    """Like :func:`make_regenerate_fn` but accumulates OpenAI usage into ``usage_acc``."""

    async def _regenerate(previous_text: str, failed_rules: list[str]) -> str:
        model = cm_answer_model()
        constraint = (
            "Your previous answer violated these rules: "
            + ", ".join(failed_rules)
            + ". Rewrite the answer, obeying every platform rule and only stating facts from KNOWN FACTS."
        )
        system_prompt = _build_system_prompt(packet) + "\n" + constraint
        response = await create_chat_completion(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": message},
                {"role": "assistant", "content": previous_text},
                {"role": "user", "content": constraint},
            ],
            max_tokens=800,
            temperature=0.2,
        )
        usage_acc.add_from_response(response, model)
        return (response.choices[0].message.content or "").strip()

    return _regenerate
