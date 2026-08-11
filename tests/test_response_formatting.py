"""Shared response-formatting guidance must stay wired into guest/owner/customer paths."""

from __future__ import annotations

from services.cm.schemas import AiBasics, AnswerPacket, StylePolicy
from services.customer_reply_v2 import answer_luna
from services.guest_ai_service import build_guest_system_prompt
from services.owner_ai_context import SYSTEM_PROMPT
from services.owner_copilot_v2.brain_support import SYSTEM_V2
from services.response_formatting import RESPONSE_FORMATTING_RULES


def test_response_formatting_rules_are_scannable_and_bilingual_safe() -> None:
    assert "OUTPUT FORMAT" in RESPONSE_FORMATTING_RULES
    assert "numbered 1 / 2 / 3" in RESPONSE_FORMATTING_RULES
    assert "dense wall" in RESPONSE_FORMATTING_RULES
    assert "Instagram" in RESPONSE_FORMATTING_RULES
    assert "AI Setup" in RESPONSE_FORMATTING_RULES
    assert "ar/en/fr" in RESPONSE_FORMATTING_RULES


def test_guest_owner_and_customer_prompts_reuse_shared_formatting() -> None:
    guest = build_guest_system_prompt(language="en", knowledge_block="")
    assert RESPONSE_FORMATTING_RULES in guest
    assert RESPONSE_FORMATTING_RULES in SYSTEM_PROMPT
    assert RESPONSE_FORMATTING_RULES in SYSTEM_V2
    # Customer IG/FB DMs + comments share Answer Tera system prompt.
    assert RESPONSE_FORMATTING_RULES in answer_luna._ANSWER_SYSTEM


def test_cm_answer_system_prompt_includes_formatting_rules() -> None:
    from services.cm.answer_generation import _build_system_prompt

    packet = AnswerPacket(
        tenant_id="t1",
        content_version_id="v1",
        index_version_id=None,
        detected_language="ar",
        response_language="ar",
        identity=AiBasics(assistant_name="Help", clinic_name="Shop"),
        style=StylePolicy(),
    )
    prompt = _build_system_prompt(packet)
    assert RESPONSE_FORMATTING_RULES in prompt
