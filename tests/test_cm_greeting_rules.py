"""Tests for CM greeting rule normalization and schema backward compat."""

from __future__ import annotations

from services.cm.greeting_rules import (
    greeting_rule_has_text,
    greeting_rule_trigger_ok,
    normalize_greeting_item,
    sanitize_dynamic_messages_payload,
)
from services.cm.schemas import DynamicMessageRecord, DynamicMessagesSection


def test_legacy_single_greeting_migrates_to_one_rule() -> None:
    legacy = {"id": "g1", "name": "Welcome", "en": "Hello!", "notes": None}
    normalized = normalize_greeting_item(legacy)
    assert normalized["enabled"] is True
    assert normalized["trigger_mode"] == "always"
    assert normalized["en"] == "Hello!"
    record = DynamicMessageRecord.model_validate(normalized)
    assert record.name == "Welcome"


def test_notes_copied_to_en_when_en_empty() -> None:
    legacy = {"id": "g2", "name": "Hi", "en": "", "notes": "Hi there!"}
    normalized = normalize_greeting_item(legacy)
    assert normalized["en"] == "Hi there!"


def test_starts_with_trigger_requires_pattern() -> None:
    rule = {
        "id": "g3",
        "trigger_mode": "starts_with",
        "trigger_pattern": "hi",
        "en": "Hi greeting",
    }
    assert greeting_rule_trigger_ok(rule) is True
    assert greeting_rule_has_text(rule) is True
    assert greeting_rule_trigger_ok({**rule, "trigger_pattern": ""}) is False


def test_any_keyword_trigger_requires_keywords() -> None:
    rule = {
        "id": "g4",
        "trigger_mode": "any_keyword",
        "keywords": ["hello", "hey"],
        "en": "Hello greeting",
    }
    assert greeting_rule_trigger_ok(rule) is True
    assert greeting_rule_trigger_ok({**rule, "keywords": []}) is False


def test_sanitize_dynamic_messages_payload_normalizes_items() -> None:
    payload = {
        "items": [{"id": "a", "name": "Rule 1", "en": "Hi"}],
        "notes": "Section note",
    }
    out = sanitize_dynamic_messages_payload(payload)
    assert len(out["items"]) == 1
    assert out["items"][0]["trigger_mode"] == "always"
    section = DynamicMessagesSection.model_validate(out)
    assert section.items[0].enabled is True
