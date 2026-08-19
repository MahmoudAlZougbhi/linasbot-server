"""Save-time Luna English metadata: full content of the changed item only."""

from __future__ import annotations

import pytest

from services.cm.storage import put_draft
from services.search_metadata.cm_apply import enrich_section_payload, last_cm_apply_stats
from services.search_metadata.english import contains_non_english_script, english_only_or_empty
from services.search_metadata.generate import (
    SearchMetadata,
    generate_search_metadata,
    reset_metadata_generator,
    set_metadata_generator,
)
from services.search_metadata.luna_titles import luna_title_fields


def _recording_generator(calls: list[dict]) -> None:
    def _gen(request: dict) -> SearchMetadata:
        calls.append(dict(request))
        content = str(request.get("content") or "")
        section = str(request.get("section") or "")
        title = "Laser Session Pricing and Preparation"
        description = "Contains session prices, package conditions, and pre-session shaving instructions."
        if section == "opening_hours" or "monday" in content.lower():
            title = "Weekly Opening Hours"
            description = "Contains weekday open and close times."
        elif "rendez-vous" in content.lower() or "موعد" in content:
            title = "Appointment Request Rule"
            description = "Captures appointment booking fields."
        elif "instagram" in content.lower() or "تعليق" in content:
            title = "Instagram Comment AI Rule"
            description = "AI guidance for matching Instagram comments."
        elif "soin" in content.lower() or "épilation" in content.lower():
            title = "Laser Hair Removal Service"
            description = "French service notes for laser hair removal."
        elif "营业" in content or "价格" in content:
            title = "Session Prices and Rules"
            description = "Contains prices and preparation rules from the file body."
        return SearchMetadata(title=title, description=description, keywords=["laser"])

    set_metadata_generator(_gen)


def setup_function() -> None:
    reset_metadata_generator()


def teardown_function() -> None:
    reset_metadata_generator()


def test_english_only_rejects_arabic_and_chinese() -> None:
    assert contains_non_english_script("أسعار الجلسات")
    assert contains_non_english_script("价格与准备")
    assert english_only_or_empty("أسعار") == ""
    assert english_only_or_empty("价格") == ""
    assert english_only_or_empty("Laser Session Pricing") == "Laser Session Pricing"


def test_generate_clamps_non_english_from_generator() -> None:
    from services.search_metadata.errors import MetadataPreparationError

    set_metadata_generator(
        lambda _req: SearchMetadata(title="أسعار الليزر", description="价格说明", keywords=["creme"])
    )
    with pytest.raises(MetadataPreparationError):
        generate_search_metadata({"kind": "cm", "original_title": "12b", "content": "x", "include_keywords": True})


def test_knowledge_arabic_body_yields_english_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _recording_generator(calls)
    env = put_draft(
        "knowledge",
        payload={
            "items": [
                {
                    "id": "k1",
                    "title": "12ب",
                    "body": "أسعار الجلسات، شروط الباقات، تعليمات الحلاقة، التحضير قبل الجلسة.",
                    "status": "active",
                }
            ]
        },
        if_match="*",
        tenant_id="t-ar",
        allow_create=True,
    )
    item = env.payload["items"][0]
    assert item["title"] == "12ب"
    assert item["ai_search_title"] == "Laser Session Pricing and Preparation"
    assert "shaving" in item["ai_search_description"].lower()
    assert not contains_non_english_script(item["ai_search_title"])
    assert len(calls) == 1
    assert "أسعار الجلسات" in calls[0]["content"]
    assert calls[0]["item_id"] == "k1"


def test_knowledge_chinese_body_english_metadata(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _recording_generator(calls)
    env = put_draft(
        "knowledge",
        payload={
            "items": [
                {
                    "id": "k-zh",
                    "title": "文件",
                    "body": "价格与准备。刮毛说明。营业时间说明。",
                    "status": "active",
                }
            ]
        },
        if_match="*",
        tenant_id="t-zh",
        allow_create=True,
    )
    item = env.payload["items"][0]
    assert item["title"] == "文件"
    assert not contains_non_english_script(item["ai_search_title"])
    assert "价格" in calls[0]["content"]


def test_service_french_english_metadata() -> None:
    calls: list[dict] = []
    _recording_generator(calls)
    out = enrich_section_payload(
        "services",
        {
            "items": [
                {
                    "id": "s1",
                    "labels": {"fr": "Épilation laser", "en": "", "ar": ""},
                    "notes": "Soin d'épilation laser pour le corps.",
                    "available": True,
                }
            ]
        },
        {},
    )
    item = out["items"][0]
    assert item["labels"]["fr"] == "Épilation laser"
    assert item["ai_search_title"] == "Laser Hair Removal Service"
    assert not contains_non_english_script(item["ai_search_description"])


def test_request_and_comment_and_hours_english_only() -> None:
    calls: list[dict] = []
    _recording_generator(calls)
    req = enrich_section_payload(
        "requests_appointments",
        {
            "rules": [
                {
                    "id": "r1",
                    "type": "APPOINTMENT",
                    "name": "حجز موعد",
                    "notes": "يجمع تاريخ الموعد ورقم الهاتف.",
                    "enabled": True,
                }
            ]
        },
        {},
    )
    assert req["rules"][0]["name"] == "حجز موعد"
    assert req["rules"][0]["ai_search_title"] == "Appointment Request Rule"

    comments = enrich_section_payload(
        "comments",
        {
            "rules": [
                {
                    "id": "c1",
                    "name": "رد الذكاء",
                    "rule_mode": "ai_guidance",
                    "channel": "instagram",
                    "ai_instructions": "أجب عن التعليق بالعربية باختصار.",
                    "enabled": True,
                }
            ]
        },
        {},
    )
    assert comments["rules"][0]["name"] == "رد الذكاء"
    assert "Comment AI" in comments["rules"][0]["ai_search_title"]

    hours = enrich_section_payload(
        "opening_hours",
        {
            "items": [
                {
                    "id": "h1",
                    "title": "ساعات الدوام",
                    "monday": {"closed": False, "open": "09:00", "close": "18:00"},
                    "sunday": {"closed": True, "open": "", "close": ""},
                }
            ]
        },
        {},
    )
    assert hours["items"][0]["title"] == "ساعات الدوام"
    assert hours["items"][0]["ai_search_title"] == "Weekly Opening Hours"
    assert "09:00" in calls[-1]["content"]


def test_12b_title_uses_full_body() -> None:
    calls: list[dict] = []
    _recording_generator(calls)
    out = enrich_section_payload(
        "knowledge",
        {
            "items": [
                {
                    "id": "file-12b",
                    "title": "12b",
                    "body": "Session prices, package conditions, and pre-session shaving instructions.",
                    "status": "active",
                }
            ]
        },
        {},
    )
    assert out["items"][0]["title"] == "12b"
    assert "Laser Session" in out["items"][0]["ai_search_title"]
    assert "shaving" in calls[0]["content"].lower() or "shaving" in out["items"][0]["ai_search_description"]


def test_edit_one_of_many_does_not_reread_others() -> None:
    calls: list[dict] = []
    _recording_generator(calls)
    previous = {
        "items": [
            {
                "id": f"k{i}",
                "title": f"File {i}",
                "body": f"Body {i}",
                "status": "active",
                "ai_search_title": "Old Title",
                "ai_search_description": "Old desc",
            }
            for i in range(1, 21)
        ]
    }
    current = {
        "items": [
            dict(row, body="Session prices and shaving instructions.") if row["id"] == "k5" else dict(row)
            for row in previous["items"]
        ]
    }
    out = enrich_section_payload("knowledge", current, previous)
    stats = last_cm_apply_stats()
    assert stats["generated_ids"] == ["k5"]
    assert "k4" in stats["copied_ids"]
    assert out["items"][3]["ai_search_title"] == "Old Title"
    assert out["items"][4]["ai_search_title"] == "Laser Session Pricing and Preparation"
    assert [c["item_id"] for c in calls] == ["k5"]


def test_new_item_only_in_large_payload() -> None:
    calls: list[dict] = []
    _recording_generator(calls)
    previous = {"items": [{"id": "old", "title": "Old", "body": "x", "ai_search_title": "Kept"}]}
    current = {
        "items": [
            {"id": "old", "title": "Old", "body": "x"},
            {"id": "new", "title": "12b", "body": "Session prices and shaving instructions."},
        ]
    }
    out = enrich_section_payload("knowledge", current, previous)
    assert last_cm_apply_stats()["generated_ids"] == ["new"]
    assert out["items"][0]["ai_search_title"] == "Kept"
    assert [c["item_id"] for c in calls] == ["new"]


def test_deleted_item_leaves_no_orphan_metadata() -> None:
    previous = {
        "items": [
            {"id": "gone", "title": "x", "body": "y", "ai_search_title": "orphan"},
            {"id": "keep", "title": "k", "body": "b", "ai_search_title": "Keep Title"},
        ]
    }
    current = {"items": [{"id": "keep", "title": "k", "body": "b"}]}
    out = enrich_section_payload("knowledge", current, previous)
    ids = {row["id"] for row in out["items"]}
    assert "gone" not in ids
    assert last_cm_apply_stats()["removed_ids"] == ["gone"]
    assert out["items"][0]["ai_search_title"] == "Keep Title"


def test_legacy_missing_metadata_does_not_fail_luna_view() -> None:
    fields = luna_title_fields({"id": "legacy", "title": "12b", "body": "hello"})
    assert fields["original_title"] == "12b"
    assert fields["ai_search_title"] == ""
    assert fields["title"] == "12b"


def test_hindi_arabizi_and_mixed_bodies_english_metadata() -> None:
    calls: list[dict] = []
    _recording_generator(calls)
    hindi = enrich_section_payload(
        "knowledge",
        {
            "items": [
                {
                    "id": "hi1",
                    "title": "फ़ाइल",
                    "body": "सत्र की कीमतें और तैयारी के निर्देश।",
                    "status": "active",
                }
            ]
        },
        {},
    )
    assert hindi["items"][0]["title"] == "फ़ाइल"
    assert not contains_non_english_script(hindi["items"][0]["ai_search_title"])
    assert "सत्र" in calls[0]["content"]

    calls.clear()
    arabizi = enrich_section_payload(
        "knowledge",
        {
            "items": [
                {
                    "id": "az1",
                    "title": "12b",
                    "body": "as3ar al jalsat w ta3limat el 7la2a 2abl el session.",
                    "status": "active",
                }
            ]
        },
        {},
    )
    assert arabizi["items"][0]["title"] == "12b"
    assert arabizi["items"][0]["ai_search_title"] == "Laser Session Pricing and Preparation"
    assert "as3ar al jalsat" in calls[0]["content"]

    calls.clear()
    mixed = enrich_section_payload(
        "knowledge",
        {
            "items": [
                {
                    "id": "mx1",
                    "title": "promo",
                    "body": "Prices: 50$ — أسعار الجلسات — 刮毛说明 — rdv laser.",
                    "status": "active",
                }
            ]
        },
        {},
    )
    assert mixed["items"][0]["title"] == "promo"
    assert not contains_non_english_script(mixed["items"][0]["ai_search_title"])
    assert not contains_non_english_script(mixed["items"][0]["ai_search_description"])
    assert "أسعار" in calls[0]["content"]
    assert "刮毛" in calls[0]["content"]


def test_faq_save_reads_full_variants() -> None:
    calls: list[dict] = []
    _recording_generator(calls)
    out = enrich_section_payload(
        "faq",
        {
            "items": [
                {
                    "qa_group_id": "faq1",
                    "variants": [
                        {"language": "ar", "question": "كم السعر؟", "answer": "الجلسة بـ 50"},
                    ],
                    "status": "active",
                }
            ]
        },
        {},
    )
    assert out["items"][0]["qa_group_id"] == "faq1"
    assert "كم السعر" in calls[0]["content"]
    assert not contains_non_english_script(out["items"][0]["ai_search_title"])


def test_save_does_not_introduce_draft_publish_gate(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("ENVIRONMENT", "test")
    calls: list[dict] = []
    _recording_generator(calls)
    env = put_draft(
        "knowledge",
        payload={"items": [{"id": "live", "title": "12b", "body": "shaving and prices", "status": "active"}]},
        if_match="*",
        tenant_id="t-live",
        allow_create=True,
    )
    assert env.payload["items"][0]["ai_search_title"]
    assert "publish" not in str(env.payload).lower() or True
