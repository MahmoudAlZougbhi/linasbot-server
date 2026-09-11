"""Luna still selects files; Terra receives original bodies including full hours."""

from __future__ import annotations

from services.cm.request_rules import format_request_rules_for_ai
from services.customer_reply_v2.retrieval_item_index import record_content
from services.search_metadata.luna_titles import luna_title_fields


def test_luna_title_fields_show_original_plus_ai() -> None:
    fields = luna_title_fields(
        {
            "id": "k1",
            "title": "12b",
            "ai_search_title": "Laser Session Pricing and Preparation",
            "ai_search_description": "Contains session prices and shaving instructions.",
        }
    )
    assert fields["original_title"] == "12b"
    assert fields["ai_search_title"].startswith("Laser")
    assert "shaving" in fields["ai_search_description"]


def test_record_content_is_original_body_not_ai_metadata() -> None:
    content = record_content(
        "knowledge",
        {
            "id": "k1",
            "title": "12b",
            "body": "Session prices and shaving instructions.",
            "ai_search_title": "Laser Session Pricing",
            "ai_search_description": "Do not use this as a price.",
        },
    )
    assert "12b" in content
    assert "Session prices and shaving instructions." in content
    assert "Do not use this as a price." not in content
    assert "Laser Session Pricing" not in content


def test_opening_hours_weekly_table_reaches_terra() -> None:
    raw = {
        "id": "h1",
        "title": "Main",
        "monday": {"closed": False, "open": "09:00", "close": "18:00"},
        "tuesday": {"closed": False, "open": "09:00", "close": "18:00"},
        "wednesday": {"closed": False, "open": "09:00", "close": "18:00"},
        "thursday": {"closed": False, "open": "09:00", "close": "18:00"},
        "friday": {"closed": False, "open": "10:00", "close": "16:00"},
        "saturday": {"closed": True, "open": "", "close": ""},
        "sunday": {"closed": True, "open": "", "close": ""},
        "ai_search_title": "Weekly Hours",
        "ai_search_description": "Hours hint only",
    }
    content = record_content("opening_hours", raw)
    for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
        assert day in content
    assert "09:00" in content
    assert "18:00" in content
    assert "Hours hint only" not in content


def test_branch_weekly_schedule_reaches_terra() -> None:
    content = record_content(
        "branches",
        {
            "id": "b1",
            "labels": {"en": "Beirut"},
            "address": "Hamra",
            "weekly_schedule": {"monday": {"enabled": True, "open": "10:00", "close": "19:00", "off_day": False}},
            "ai_search_description": "not a fact",
        },
    )
    assert "weekly_schedule" in content
    assert "10:00" in content
    assert "not a fact" not in content


def test_branch_attachments_reach_terra_without_urls() -> None:
    content = record_content(
        "branches",
        {
            "id": "b2",
            "labels": {"en": "Hamra"},
            "weekly_schedule": {"tuesday": {"enabled": True, "open": "09:00", "close": "18:00", "off_day": False}},
            "attachments": [
                {
                    "id": "att1",
                    "kind": "image",
                    "title": "Parking map",
                    "description": "Back entrance parking",
                    "url": "https://secret.example/map.jpg",
                    "status": "active",
                }
            ],
        },
    )
    assert "Parking map" in content
    assert "Back entrance parking" in content
    assert "secret.example" not in content
    assert '"type": "image"' in content or '"type":"image"' in content.replace(" ", "")


def test_request_rules_only_selected_reach_terra() -> None:
    payload = {
        "rules": [
            {"id": f"r{i}", "type": "APPOINTMENT", "name": f"Rule {i}", "notes": "n", "enabled": True}
            for i in range(600)
        ]
    }
    dumped = format_request_rules_for_ai(payload, selected_ids=["requests_appointments:r7", "r8"])
    assert dumped.count("- [APPOINTMENT]") == 2
    assert "Rule 7" in dumped
    assert "Rule 8" in dumped
    assert "Rule 599" not in dumped
    empty = format_request_rules_for_ai(payload, selected_ids=[])
    assert "Do not assume" in empty
    assert "Rule 1" not in empty
