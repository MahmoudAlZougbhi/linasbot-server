"""Requests HUMAN type + Franco replies in Arabic script."""

import pytest

from services.ai_setup.language_policy import resolve_customer_response_language
from services.ai_setup.progress_quality import assess_section_fill
from services.ai_setup.request_rules import normalize_request_rule_item
from services.ai_setup.setup_chat import SETUP_SECTION_ORDER
from services.brain.planner.heuristic import plan_message
from services.owner_copilot.setup_flow import SETUP_SECTIONS
from services.requests.constants import PERSISTABLE_REQUEST_TYPES, REQUEST_TYPES
from services.requests.request_graphs.compiler import destination_from_type


def test_human_is_a_request_type() -> None:
    assert "HUMAN" in REQUEST_TYPES
    assert "HUMAN" not in PERSISTABLE_REQUEST_TYPES
    row = normalize_request_rule_item({"id": "h1", "type": "human", "name": "Staff"})
    assert row["type"] == "HUMAN"
    assert destination_from_type("HUMAN") == "live_chat"


def test_human_intent_matches_owner_examples() -> None:
    assert destination_from_type("HUMAN") == "live_chat"

    def types(message: str) -> set[str]:
        return {task.type for task in plan_message(message).tasks}

    assert types("I want to speak with an agent") == {"information"}
    assert "human_request" not in types("what is the price")


def test_franco_reply_language_is_arabic_script() -> None:
    assert resolve_customer_response_language(tenant_id=None, detected_language="franco") == "ar"
    assert resolve_customer_response_language(tenant_id=None, detected_language="en") == "en"
    assert resolve_customer_response_language(tenant_id=None, detected_language="fr") == "fr"


def test_owner_setup_does_not_interview_languages() -> None:
    assert "languages" not in SETUP_SECTION_ORDER
    assert "languages" not in SETUP_SECTIONS
    assert "ai_limits" not in SETUP_SECTIONS
    assert "ai_limits" not in SETUP_SECTION_ORDER
    quality = assess_section_fill("languages", {}, is_default=True)
    assert quality["is_done"] is True
    assert quality["gaps"] == []


@pytest.mark.asyncio
async def test_copilot_cannot_patch_languages(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.tools_write import tool_propose_cm_patch

    monkeypatch.setattr(
        "services.owner_copilot.tools_write.resolve_permissions",
        lambda role, _extra: {"contentManagers": True},
    )
    blocked = await tool_propose_cm_patch(
        tenant_id="t1",
        role="admin",
        user_id="u1",
        section="languages",
        patch={"default_language": "en", "supported_languages": ["en"]},
    )
    assert blocked.ok is False
    assert blocked.error == "languages_not_owner_configurable"
