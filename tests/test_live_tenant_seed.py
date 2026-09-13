"""Isolated live-test tenant clocks and markers must not mix."""

from __future__ import annotations

from services.customer_ai.evals.live_tenant_matrix import capture_ids
from services.customer_ai.evals.live_tenant_seed import (
    MARKER_LINAS,
    MARKER_TEST,
    MARKER_TEST_2,
    keep_knowledge_item,
    merge_linas_hours,
    scrub_internal_rules,
    test1_sections,
    test2_sections,
    week,
)


def test_linas_hours_patch_keeps_seven_days() -> None:
    payload = merge_linas_hours({"items": [{"id": "antelias", "labels": {"en": "Antelias"}}]})
    antelias = next(row for row in payload["items"] if row["id"] == "antelias")
    sunday = antelias["weekly_schedule"]["sunday"]
    assert sunday["off_day"] is False
    assert sunday["open"] == "11:00"
    assert sunday["close"] == "19:00"
    beirut = next(row for row in payload["items"] if row["id"] == "beirut")
    assert beirut["weekly_schedule"]["sunday"]["open"] == "10:00"


def test_test_tenants_have_distinct_prices_and_markers() -> None:
    one = test1_sections()
    two = test2_sections()
    assert one["prices"]["price_entries"][0]["amount"] == 99
    assert two["prices"]["price_entries"][0]["amount"] == 5
    assert MARKER_TEST in one["knowledge"]["items"][0]["body"]
    assert MARKER_TEST_2 in two["knowledge"]["items"][0]["body"]
    assert MARKER_LINAS not in one["knowledge"]["items"][0]["body"]
    assert one["requests_appointments"]["enabled_types"] == ["ORDER"]
    assert two["requests_appointments"]["enabled_types"] == ["HUMAN"]
    hamra = week("09:00", "15:00", sunday_off=True)
    assert hamra["sunday"]["off_day"] is True


def test_capture_ids_use_lab_prefix() -> None:
    ids = capture_ids("abcd1234")
    assert ids["conversation_id"].startswith("lab:")
    assert ids["user_id"].startswith("lab:")
    assert ids["message_id"].startswith("lab:")
    assert ids["channel"] == "instagram_dm"


def test_internal_greeting_rule_is_dropped() -> None:
    assert keep_knowledge_item({"body": "Street parking. Code X."}) is True
    assert keep_knowledge_item({"body": "Use this rule only if the user message is only a casual greeting."}) is False
    scrubbed = scrub_internal_rules(
        {"knowledge": {"items": [{"id": "greet_policy", "body": "Use this rule only if the user message is only x"}]}}
    )
    assert scrubbed["knowledge"]["items"] == []
