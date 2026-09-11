"""Requests HUMAN type + Franco replies in Arabic script."""

import pytest

from services.cm.progress_quality import assess_section_fill
from services.cm.query_interpreter import HUMAN_INTENT_RE
from services.cm.request_rules import normalize_request_rule_item
from services.cm.setup_chat import SETUP_SECTION_ORDER
from services.cm.language_policy import resolve_customer_response_language
from services.owner_copilot_v2.setup_flow import SETUP_SECTIONS
from services.request_graphs.compiler import destination_from_type
from services.requests.constants import REQUEST_TYPES


def test_human_is_a_request_type() -> None:
    assert "HUMAN" in REQUEST_TYPES
    row = normalize_request_rule_item({"id": "h1", "type": "human", "name": "Staff"})
    assert row["type"] == "HUMAN"
    assert destination_from_type("HUMAN") == "live_chat"


def test_human_intent_matches_owner_examples() -> None:
    assert HUMAN_INTENT_RE.search("human")
    assert HUMAN_INTENT_RE.search("I want an agent")
    assert HUMAN_INTENT_RE.search("بدي موظف")
    assert HUMAN_INTENT_RE.search("أريد أتحدث مع شخص")
    assert not HUMAN_INTENT_RE.search("what is the price")


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
    from services.owner_ai_tools_write import tool_propose_cm_patch

    monkeypatch.setattr(
        "services.owner_ai_tools_write.resolve_permissions",
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
