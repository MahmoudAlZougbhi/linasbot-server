"""Save + Luna title view + Terra original body for each Customer Reply section."""

from __future__ import annotations

from services.search_metadata.cm_apply import enrich_section_payload, last_cm_apply_stats
from services.search_metadata.english import contains_non_english_script, looks_like_english
from services.search_metadata.generate import SearchMetadata, reset_metadata_generator, set_metadata_generator
from services.search_metadata.luna_titles import luna_title_fields
from services.customer_reply_v2.retrieval_item_index import record_content


def setup_function() -> None:
    reset_metadata_generator()
    set_metadata_generator(
        lambda req: SearchMetadata(
            title="English Search Title",
            description="Contains the grounded item content for routing.",
        )
    )


def teardown_function() -> None:
    reset_metadata_generator()


def _assert_meta(item: dict) -> None:
    fields = luna_title_fields(item)
    assert looks_like_english(item["ai_search_title"])
    assert looks_like_english(item["ai_search_description"])
    assert not contains_non_english_script(item["ai_search_title"])
    assert fields["original_title"]
    assert fields["ai_search_title"] == item["ai_search_title"]


def test_each_section_save_reads_only_that_item() -> None:
    cases = [
        (
            "knowledge",
            {"items": [{"id": "k1", "title": "12b", "body": "أسعار الجلسات وتعليمات الحلاقة", "status": "active"}]},
        ),
        (
            "services",
            {"items": [{"id": "s1", "labels": {"fr": "Soin"}, "notes": "Épilation laser", "available": True}]},
        ),
        (
            "branches",
            {
                "items": [
                    {
                        "id": "b1",
                        "labels": {"ar": "فرع 2"},
                        "address": "Hamra",
                        "weekly_schedule": {"monday": {"enabled": True, "open": "09:00", "close": "18:00"}},
                    }
                ]
            },
        ),
        (
            "opening_hours",
            {"items": [{"id": "h1", "title": "ساعات", "monday": {"closed": False, "open": "09:00", "close": "18:00"}}]},
        ),
        (
            "dynamic_messages",
            {"items": [{"id": "g1", "name": "ترحيب", "en": "Hello", "ar": "مرحبا", "enabled": True}]},
        ),
        (
            "requests_appointments",
            {"rules": [{"id": "r1", "type": "APPOINTMENT", "name": "حجز", "notes": "موعد", "enabled": True}]},
        ),
        (
            "requests_appointments",
            {"rules": [{"id": "ord1", "type": "ORDER", "name": "طلب شراء", "notes": "يجمع المنتج والعنوان", "enabled": True}]},
        ),
        (
            "comments",
            {
                "rules": [
                    {
                        "id": "c1",
                        "name": "رد",
                        "rule_mode": "ai_guidance",
                        "ai_instructions": "أجب باختصار",
                        "enabled": True,
                    }
                ]
            },
        ),
        (
            "off_days",
            {"rules": [{"id": "o1", "kind": "weekly", "weekday": 6, "reason": "عطلة الأحد"}]},
        ),
    ]
    for section, payload in cases:
        other = dict(payload)
        # second unchanged sibling when list exists
        key = "items" if "items" in payload else "rules"
        if len(payload[key]) == 1:
            sibling = dict(payload[key][0])
            sibling["id"] = "other"
            sibling["ai_search_title"] = "Kept Title"
            sibling["ai_search_description"] = "Kept description."
            previous = {key: [sibling]}
            current = {key: [sibling, payload[key][0]]}
        else:
            previous = {}
            current = payload
        out = enrich_section_payload(section, current, previous)
        stats = last_cm_apply_stats()
        assert stats["generated_ids"] == [payload[key][0].get("id") or payload[key][0].get("qa_group_id")]
        item = next(row for row in out[key] if row.get("id") == payload[key][0].get("id"))
        _assert_meta(item)
        body = record_content(section, item)
        assert item["ai_search_title"] not in body
        assert item["ai_search_description"] not in body
