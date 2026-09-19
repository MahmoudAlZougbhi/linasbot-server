"""Shared response-formatting guidance must stay wired into guest/owner/customer paths."""

from __future__ import annotations

from services.guest.guest_ai_service import build_guest_system_prompt
from services.owner_copilot.response_formatting import RESPONSE_FORMATTING_RULES
from services.owner_copilot.sol_seed import SOL_SEED_ADVANCED


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
    assert RESPONSE_FORMATTING_RULES in SOL_SEED_ADVANCED
