"""Save in AI Setup must become customer-live without a second Publish/Live tap."""

from __future__ import annotations

from typing import Any

import pytest

from services.cm.save_live import put_draft_and_go_live
from services.cm.storage import get_draft, put_draft
from services.cm.version_store import load_published_content, read_published_pointer
from services.search_metadata.cm_apply import last_cm_apply_stats
from services.search_metadata.generate import SearchMetadata, reset_metadata_generator, set_metadata_generator

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


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


async def _save(section: str, payload: dict[str, Any], tenant_id: str, etag: str | None = None):
    match = etag
    if not match:
        env = get_draft(section, tenant_id=tenant_id, create_default=True)
        match = env.etag
    envelope, activation = await put_draft_and_go_live(
        section=section,
        payload=payload,
        if_match=match,
        tenant_id=tenant_id,
        updated_by="tester",
    )
    assert activation.get("live") is True, activation
    return envelope, activation


def _published(tenant_id: str) -> dict[str, Any]:
    _pointer, sections = load_published_content(tenant_id)
    return sections


@pytest.mark.asyncio
async def test_knowledge_save_is_live_for_luna_without_extra_publish(v2_env) -> None:
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    tid = "t_save_live_kn"
    first = {
        "items": [
            {"id": "k1", "title": "12b", "body": "سعر الجلسة 50", "status": "active"},
            {"id": "k2", "title": "other", "body": "unchanged", "status": "active"},
        ]
    }
    env, _ = await _save("knowledge", first, tid)
    second = {
        "items": [
            {"id": "k1", "title": "12b", "body": "سعر الجلسة صار 80 دولار بعد التعديل", "status": "active"},
            {"id": "k2", "title": "other", "body": "unchanged", "status": "active"},
        ]
    }
    await _save("knowledge", second, tid, etag=env.etag)
    stats = last_cm_apply_stats()
    assert stats["generated_ids"] == ["k1"]
    live = _published(tid)["knowledge"]["items"]
    row = next(item for item in live if item["id"] == "k1")
    assert "80 دولار" in row["body"]
    assert row["ai_search_title"] == "English Search Title"
    retrieval = await run_retrieval_luna(
        tenant_id=tid,
        message="قديش سعر الجلسة؟",
        customer_profile={},
        scripted_tool_calls=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": ["knowledge:k1"]}}],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["knowledge:k1"]}},
        ],
    )
    blob = " ".join(e.content for e in retrieval.evidence)
    assert "80 دولار" in blob
    assert "50" not in blob or "80" in blob
    assert "English Search Title" not in blob


@pytest.mark.asyncio
async def test_new_branch_save_is_immediately_selectable(v2_env) -> None:
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    tid = "t_save_live_br"
    await _save(
        "branches",
        {
            "items": [
                {
                    "id": "br_saida",
                    "labels": {"ar": "فرع 2", "en": "Branch 2"},
                    "address": "Saida waterfront",
                    "maps_url": "https://maps.example/saida",
                    "notes": "Parking behind the building",
                    "available": True,
                    "weekly_schedule": {
                        "monday": {"enabled": True, "open": "09:00", "close": "18:00", "off_day": False}
                    },
                }
            ]
        },
        tid,
    )
    live = _published(tid)["branches"]["items"]
    assert live[0]["id"] == "br_saida"
    assert live[0]["ai_search_title"] == "English Search Title"
    retrieval = await run_retrieval_luna(
        tenant_id=tid,
        message="وين فرع صيدا؟",
        customer_profile={},
        scripted_tool_calls=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": ["branches:br_saida"]}}],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["branches:br_saida"]}},
        ],
    )
    assert [e.source_id for e in retrieval.evidence] == ["branches:br_saida"]
    assert "Saida waterfront" in retrieval.evidence[0].content


@pytest.mark.asyncio
async def test_hours_save_replaces_old_hours_for_tera(v2_env) -> None:
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    tid = "t_save_live_oh"
    old = {
        "items": [
            {
                "id": "oh_beirut",
                "title": "ساعات بيروت",
                "monday": {"closed": False, "open": "09:00", "close": "17:00"},
                "sunday": {"closed": True, "open": "", "close": ""},
            }
        ]
    }
    env, _ = await _save("opening_hours", old, tid)
    new = {
        "items": [
            {
                "id": "oh_beirut",
                "title": "ساعات بيروت",
                "monday": {"closed": False, "open": "11:00", "close": "19:00"},
                "sunday": {"closed": True, "open": "", "close": ""},
            }
        ]
    }
    await _save("opening_hours", new, tid, etag=env.etag)
    live = _published(tid)["opening_hours"]["items"][0]
    assert live["monday"]["open"] == "11:00"
    retrieval = await run_retrieval_luna(
        tenant_id=tid,
        message="فرع بيروت لأي ساعة فاتح؟",
        customer_profile={},
        scripted_tool_calls=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": ["opening_hours:oh_beirut"]}}],
            {
                "final_plan": {
                    "evidence_status": "sufficient",
                    "selected_source_ids": ["opening_hours:oh_beirut"],
                }
            },
        ],
    )
    blob = retrieval.evidence[0].content
    assert "11:00" in blob
    assert "19:00" in blob
    assert "09:00" not in blob


@pytest.mark.asyncio
async def test_appointment_rule_save_is_live_for_next_message(v2_env) -> None:
    from services.cm.request_rules import format_request_rules_for_ai
    from services.requests.config_loader import load_published_requests_config

    tid = "t_save_live_req"
    payload = {
        "module_enabled": True,
        "enabled_types": ["APPOINTMENT"],
        "rules": [
            {
                "id": "appt1",
                "type": "APPOINTMENT",
                "name": "حجز",
                "notes": "يجمع التاريخ القديم",
                "enabled": True,
            }
        ],
    }
    env, _ = await _save("requests_appointments", payload, tid)
    payload["rules"][0]["notes"] = "يجمع التاريخ والهاتف بعد التعديل"
    await _save("requests_appointments", payload, tid, etag=env.etag)
    cfg = load_published_requests_config(tid) or {}
    guidance = format_request_rules_for_ai(cfg, selected_ids=["requests_appointments:appt1"])
    assert "بعد التعديل" in guidance
    assert "القديم" not in guidance


@pytest.mark.asyncio
async def test_comment_ai_rule_save_used_on_next_comment(v2_env) -> None:
    from services.customer_reply_v2.comment_rule_engine import evaluate_published_comment_engine

    tid = "t_save_live_cmt"
    payload = {
        "default_action": "reply_comment",
        "policy_text": "",
        "rules": [
            {
                "id": "c_ai",
                "name": "رد",
                "enabled": True,
                "keywords": ["price"],
                "rule_mode": "ai_guidance",
                "ai_instructions": "أجب باختصار من الكتالوج القديم",
                "channel": "instagram",
                "scope": "all_posts",
            }
        ],
    }
    env, _ = await _save("comments", payload, tid)
    payload["rules"][0]["ai_instructions"] = "أجب من الكتالوج الجديد فقط"
    await _save("comments", payload, tid, etag=env.etag)
    result = evaluate_published_comment_engine(
        tid,
        comment_text="what is the price?",
        channel="instagram_comment",
        post_id="POST",
    )
    assert result.rule_mode == "ai_guidance"
    assert result.ai_guidance_rules[0]["ai_instructions"] == "أجب من الكتالوج الجديد فقط"


@pytest.mark.asyncio
async def test_deleted_item_is_not_selectable_after_save(v2_env) -> None:
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    tid = "t_save_live_del"
    env, act = await _save(
        "knowledge",
        {
            "items": [
                {"id": "keep", "title": "keep", "body": "stay", "status": "active"},
                {"id": "gone", "title": "gone", "body": "remove me", "status": "active"},
            ]
        },
        tid,
    )
    await _save(
        "knowledge",
        {"items": [{"id": "keep", "title": "keep", "body": "stay", "status": "active"}]},
        tid,
        etag=env.etag,
    )
    stats = last_cm_apply_stats()
    assert "gone" in stats["removed_ids"]
    ids = {row["id"] for row in _published(tid)["knowledge"]["items"]}
    assert ids == {"keep"}
    ctx = ToolContext(tenant_id=tid, published_revision=act["content_version_id"], channel="instagram_dm")
    # published revision changed; load current pointer
    pointer = read_published_pointer(tid)
    assert pointer is not None
    ctx.published_revision = pointer.content_version_id
    out = dispatch_retrieval_tool("read_published_cm_items", {"item_ids": ["knowledge:gone"]}, ctx)
    assert out["data"]["evidence"] == []
    assert "gone" in str(out["data"]["rejected_item_ids"])


@pytest.mark.asyncio
async def test_greeting_and_service_save_go_live(v2_env) -> None:
    tid = "t_save_live_misc"
    await _save(
        "dynamic_messages",
        {"items": [{"id": "g1", "name": "ترحيب", "en": "Hello", "ar": "مرحبا", "enabled": True}]},
        tid,
    )
    await _save(
        "services",
        {"items": [{"id": "s1", "labels": {"fr": "Soin"}, "notes": "Épilation laser", "available": True}]},
        tid,
    )
    sections = _published(tid)
    assert sections["dynamic_messages"]["items"][0]["ar"] == "مرحبا"
    assert sections["dynamic_messages"]["items"][0]["ai_search_title"] == "English Search Title"
    assert sections["services"]["items"][0]["id"] == "s1"


@pytest.mark.asyncio
async def test_empty_metadata_still_publishes_complete_item(v2_env) -> None:
    reset_metadata_generator()
    tid = "t_save_live_meta_fail"
    await _save(
        "knowledge",
        {"items": [{"id": "k9", "title": "12b", "body": "محتوى كامل", "status": "active"}]},
        tid,
    )
    row = _published(tid)["knowledge"]["items"][0]
    assert row["body"] == "محتوى كامل"
    assert row["title"] == "12b"
    assert not row.get("ai_search_title")


@pytest.mark.asyncio
async def test_failed_activation_does_not_flip_live_pointer(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    tid = "t_save_live_fail"
    env, first = await _save(
        "knowledge",
        {"items": [{"id": "k1", "title": "old", "body": "old body", "status": "active"}]},
        tid,
    )
    old_id = first["content_version_id"]

    async def _blocked(**_kwargs):
        return {"live": False, "reason": "publish_blocked", "message": "blocked"}

    monkeypatch.setattr("services.cm.save_live.go_live_saved_section", _blocked)
    from services.cm.save_live import put_draft_and_go_live as _save_fn

    envelope, activation = await _save_fn(
        section="knowledge",
        payload={"items": [{"id": "k1", "title": "old", "body": "NEW body never live", "status": "active"}]},
        if_match=env.etag,
        tenant_id=tid,
        updated_by="tester",
    )
    assert activation.get("live") is False
    pointer = read_published_pointer(tid)
    assert pointer is not None
    assert pointer.content_version_id == old_id
    live = _published(tid)["knowledge"]["items"][0]
    assert live["body"] == "old body"
    draft = get_draft("knowledge", tenant_id=tid, create_default=False)
    assert draft.payload["items"][0]["body"] == "NEW body never live"
    assert envelope.etag == draft.etag


@pytest.mark.asyncio
async def test_plain_put_draft_without_save_live_is_not_customer_live(v2_env) -> None:
    tid = "t_save_live_control"
    await _save(
        "knowledge",
        {"items": [{"id": "k1", "title": "live", "body": "published body", "status": "active"}]},
        tid,
    )
    env = get_draft("knowledge", tenant_id=tid, create_default=False)
    put_draft(
        "knowledge",
        payload={"items": [{"id": "k1", "title": "live", "body": "draft only", "status": "active"}]},
        if_match=env.etag,
        tenant_id=tid,
        updated_by="tester",
    )
    live = _published(tid)["knowledge"]["items"][0]
    assert live["body"] == "published body"
