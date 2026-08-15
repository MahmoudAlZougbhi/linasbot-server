"""Tests for CM request rule normalization and legacy migration."""

from __future__ import annotations

from services.cm.request_rules import (
    format_request_rules_for_ai,
    migrate_legacy_to_rules,
    normalize_request_rule_item,
    request_rule_has_content,
    sanitize_requests_appointments_payload,
)
from services.cm.schemas import LocalizedLabels, RequestsAppointmentsSection
from services.cm.schemas_requests import RequestRule


def test_normalize_request_rule_defaults_type() -> None:
    rule = normalize_request_rule_item({"id": "r1", "name": "Book laser"})
    assert rule["type"] == "APPOINTMENT"
    assert rule["enabled"] is True
    assert rule["name"] == "Book laser"


def test_migrate_legacy_enabled_types_to_rules() -> None:
    legacy = {
        "module_enabled": True,
        "enabled_types": ["APPOINTMENT", "ORDER"],
        "type_labels": {"ORDER": LocalizedLabels(en="Product order").model_dump(mode="json")},
        "notes": "Collect phone and preferred date.",
        "fields": [{"id": "phone", "required": True}],
    }
    rules = migrate_legacy_to_rules(legacy)
    assert len(rules) == 2
    assert rules[0]["type"] == "APPOINTMENT"
    assert rules[1]["type"] == "ORDER"
    assert rules[1]["name"] == "Product order"
    assert rules[0]["notes"] == "Collect phone and preferred date."


def test_sanitize_derives_module_and_preserves_hidden_fields() -> None:
    payload = {
        "module_enabled": False,
        "enabled_types": [],
        "rules": [
            {"id": "r1", "type": "OTHER", "name": "Custom", "notes": "Ask details first."},
        ],
        "services": [{"id": "svc1", "labels": {"en": "Legacy service"}, "enabled": True}],
        "messages": {"acknowledgment": "Thanks"},
    }
    out = sanitize_requests_appointments_payload(payload)
    assert out["module_enabled"] is True
    assert out["enabled_types"] == ["OTHER"]
    assert out["services"][0]["id"] == "svc1"
    assert out["messages"]["acknowledgment"] == "Thanks"
    assert isinstance(out["fields"], list) and out["fields"]


def test_explicit_empty_rules_do_not_migrate_legacy_types() -> None:
    rules = migrate_legacy_to_rules({"enabled_types": ["ORDER"], "rules": []})
    assert rules == []


def test_sanitize_clears_module_when_no_rules() -> None:
    out = sanitize_requests_appointments_payload(
        {
            "module_enabled": True,
            "enabled_types": ["ORDER"],
            "rules": [],
        }
    )
    assert out["module_enabled"] is False
    assert out["enabled_types"] == []


def test_schema_accepts_rules() -> None:
    section = RequestsAppointmentsSection(
        rules=[RequestRule(id="r1", type="APPOINTMENT", name="Booking", notes="Ask date")],
        module_enabled=True,
        enabled_types=["APPOINTMENT"],
    )
    dumped = section.model_dump(mode="json")
    assert dumped["rules"][0]["name"] == "Booking"
    RequestsAppointmentsSection.model_validate(dumped)


def test_format_request_rules_for_ai() -> None:
    text = format_request_rules_for_ai(
        {
            "rules": [
                {"id": "r1", "type": "ORDER", "name": "Shop", "notes": "Collect items", "enabled": True},
            ]
        }
    )
    assert "[ORDER]" in text
    assert "Shop" in text
    assert "Collect items" in text


def test_request_rule_has_content() -> None:
    assert request_rule_has_content({"name": "x"}) is True
    assert request_rule_has_content({"notes": "y"}) is True
    assert request_rule_has_content({}) is False
