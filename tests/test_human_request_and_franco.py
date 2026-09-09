"""Requests HUMAN type + Franco replies in Arabic script."""

from services.cm.query_interpreter import HUMAN_INTENT_RE
from services.cm.request_rules import normalize_request_rule_item
from services.customer_reply_v2.answer_luna import effective_response_language
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
    assert effective_response_language(response_language="franco") == "ar"
    assert effective_response_language(response_language="en") == "en"
    assert effective_response_language(response_language="fr") == "fr"
