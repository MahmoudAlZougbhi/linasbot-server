"""Save must fail closed when search metadata is not ready — no live flip."""

from __future__ import annotations

from typing import Any

import pytest

from services.cm.save_live import put_draft_and_go_live
from services.cm.storage import get_draft
from services.cm.version_store import load_published_content, read_published_pointer
from services.search_metadata.errors import METADATA_PREPARATION_MESSAGE, MetadataPreparationError
from services.search_metadata.generate import SearchMetadata, reset_metadata_generator, set_metadata_generator

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)

SECTION_CASES: list[tuple[str, dict[str, Any]]] = [
    ("knowledge", {"items": [{"id": "k1", "title": "12b", "body": "أسعار الجلسات", "status": "active"}]}),
    ("services", {"items": [{"id": "s1", "labels": {"fr": "Soin"}, "notes": "Épilation laser", "available": True}]}),
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
    ("dynamic_messages", {"items": [{"id": "g1", "name": "ترحيب", "en": "Hello", "ar": "مرحبا", "enabled": True}]}),
    (
        "requests_appointments",
        {
            "module_enabled": True,
            "enabled_types": ["APPOINTMENT"],
            "rules": [{"id": "r1", "type": "APPOINTMENT", "name": "حجز", "notes": "موعد", "enabled": True}],
        },
    ),
    (
        "comments",
        {
            "default_action": "reply_comment",
            "policy_text": "",
            "rules": [
                {
                    "id": "c1",
                    "name": "رد",
                    "rule_mode": "ai_guidance",
                    "ai_instructions": "أجب باختصار",
                    "enabled": True,
                    "keywords": ["price"],
                    "channel": "instagram",
                    "scope": "all_posts",
                }
            ],
        },
    ),
]


def _ok_gen() -> None:
    set_metadata_generator(
        lambda _req: SearchMetadata(
            title="English Search Title",
            description="Contains the grounded item content for routing.",
        )
    )


def _fail_gen(meta: SearchMetadata) -> None:
    reset_metadata_generator()
    set_metadata_generator(lambda _req: meta)


def _published(tenant_id: str) -> dict[str, Any]:
    _pointer, sections = load_published_content(tenant_id)
    return sections


async def _save(section: str, payload: dict[str, Any], tenant_id: str, etag: str | None = None):
    match = etag
    if not match:
        env = get_draft(section, tenant_id=tenant_id, create_default=True)
        match = env.etag
    return await put_draft_and_go_live(
        section=section,
        payload=payload,
        if_match=match,
        tenant_id=tenant_id,
        updated_by="tester",
    )


def _list_key(payload: dict[str, Any]) -> str:
    return "items" if "items" in payload else "rules"


def setup_function() -> None:
    _ok_gen()


def teardown_function() -> None:
    reset_metadata_generator()


@pytest.mark.asyncio
async def test_edit_success_goes_live_immediately(v2_env) -> None:
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    tid = "t_meta_ok"
    env, _ = await _save(
        "knowledge",
        {"items": [{"id": "k1", "title": "12b", "body": "السعر القديم 40", "status": "active"}]},
        tid,
    )
    await _save(
        "knowledge",
        {"items": [{"id": "k1", "title": "12b", "body": "السعر الجديد 80 دولار", "status": "active"}]},
        tid,
        etag=env.etag,
    )
    live = _published(tid)["knowledge"]["items"][0]
    assert "80 دولار" in live["body"]
    assert live["ai_search_title"] == "English Search Title"
    retrieval = await run_retrieval_luna(
        tenant_id=tid,
        message="قديش السعر؟",
        customer_profile={},
        scripted_tool_calls=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": ["knowledge:k1"]}}],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["knowledge:k1"]}},
        ],
    )
    blob = " ".join(e.content for e in retrieval.evidence)
    assert "80 دولار" in blob
    assert "English Search Title" not in blob


@pytest.mark.asyncio
async def test_edit_metadata_fail_keeps_old_live(v2_env) -> None:
    tid = "t_meta_fail_edit"
    env, first = await _save(
        "knowledge",
        {"items": [{"id": "k1", "title": "12b", "body": "السعر القديم 40", "status": "active"}]},
        tid,
    )
    old_id = first["content_version_id"]
    _fail_gen(SearchMetadata(title="", description=""))
    with pytest.raises(MetadataPreparationError) as exc:
        await _save(
            "knowledge",
            {"items": [{"id": "k1", "title": "12b", "body": "السعر الجديد يجب ألا يظهر", "status": "active"}]},
            tid,
            etag=env.etag,
        )
    assert "luna" not in str(exc.value).lower()
    assert read_published_pointer(tid).content_version_id == old_id
    live = _published(tid)["knowledge"]["items"][0]
    assert live["body"] == "السعر القديم 40"
    draft = get_draft("knowledge", tenant_id=tid, create_default=False)
    assert draft.payload["items"][0]["body"] == "السعر القديم 40"


@pytest.mark.asyncio
async def test_empty_title_keeps_old_live(v2_env) -> None:
    tid = "t_meta_empty_title"
    env, first = await _save(
        "knowledge",
        {"items": [{"id": "k1", "title": "old", "body": "old body", "status": "active"}]},
        tid,
    )
    _fail_gen(SearchMetadata(title="", description="Contains a short English summary of the file."))
    with pytest.raises(MetadataPreparationError):
        await _save(
            "knowledge",
            {"items": [{"id": "k1", "title": "old", "body": "new body", "status": "active"}]},
            tid,
            etag=env.etag,
        )
    assert _published(tid)["knowledge"]["items"][0]["body"] == "old body"
    assert first["content_version_id"] == read_published_pointer(tid).content_version_id


@pytest.mark.asyncio
async def test_empty_description_keeps_old_live(v2_env) -> None:
    tid = "t_meta_empty_desc"
    env, _ = await _save(
        "knowledge",
        {"items": [{"id": "k1", "title": "old", "body": "old body", "status": "active"}]},
        tid,
    )
    _fail_gen(SearchMetadata(title="English Search Title", description=""))
    with pytest.raises(MetadataPreparationError):
        await _save(
            "knowledge",
            {"items": [{"id": "k1", "title": "old", "body": "new body", "status": "active"}]},
            tid,
            etag=env.etag,
        )
    assert _published(tid)["knowledge"]["items"][0]["body"] == "old body"


@pytest.mark.asyncio
async def test_non_english_twice_does_not_save_empty_metadata(v2_env) -> None:
    tid = "t_meta_fr"
    env, _ = await _save(
        "knowledge",
        {"items": [{"id": "k1", "title": "old", "body": "old body", "status": "active"}]},
        tid,
    )
    _fail_gen(SearchMetadata(title="Horaires d'ouverture", description="Contient les heures"))
    with pytest.raises(MetadataPreparationError):
        await _save(
            "knowledge",
            {"items": [{"id": "k1", "title": "old", "body": "new body", "status": "active"}]},
            tid,
            etag=env.etag,
        )
    live = _published(tid)["knowledge"]["items"][0]
    assert live["body"] == "old body"
    assert live["ai_search_title"] == "English Search Title"
    assert live["ai_search_description"]


@pytest.mark.asyncio
async def test_new_item_metadata_fail_is_not_live_or_listed(v2_env) -> None:
    from services.customer_reply_v2.operational_titles import collect_operational_titles

    tid = "t_meta_new_fail"
    env, _ = await _save(
        "knowledge",
        {"items": [{"id": "k_old", "title": "old", "body": "old body", "status": "active"}]},
        tid,
    )
    _fail_gen(SearchMetadata())
    with pytest.raises(MetadataPreparationError):
        await _save(
            "knowledge",
            {
                "items": [
                    {"id": "k_old", "title": "old", "body": "old body", "status": "active"},
                    {"id": "k_new", "title": "12b", "body": "ملف جديد", "status": "active"},
                ]
            },
            tid,
            etag=env.etag,
        )
    ids = {row["id"] for row in _published(tid)["knowledge"]["items"]}
    assert ids == {"k_old"}
    listed = {row.get("id") for row in collect_operational_titles(_published(tid))}
    assert "knowledge:k_new" not in listed


@pytest.mark.asyncio
async def test_new_item_success_is_immediately_live(v2_env) -> None:
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    tid = "t_meta_new_ok"
    env, _ = await _save(
        "knowledge",
        {"items": [{"id": "k_old", "title": "old", "body": "old body", "status": "active"}]},
        tid,
    )
    await _save(
        "knowledge",
        {
            "items": [
                {"id": "k_old", "title": "old", "body": "old body", "status": "active"},
                {"id": "k_new", "title": "12b", "body": "الملف الجديد للزبون", "status": "active"},
            ]
        },
        tid,
        etag=env.etag,
    )
    ids = {row["id"] for row in _published(tid)["knowledge"]["items"]}
    assert "k_new" in ids
    retrieval = await run_retrieval_luna(
        tenant_id=tid,
        message="الملف الجديد",
        customer_profile={},
        scripted_tool_calls=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": ["knowledge:k_new"]}}],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["knowledge:k_new"]}},
        ],
    )
    assert "الملف الجديد للزبون" in retrieval.evidence[0].content


@pytest.mark.asyncio
async def test_bad_title_12b_success_then_failure(v2_env) -> None:
    from services.customer_reply_v2.operational_titles import collect_operational_titles
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    tid = "t_meta_12b"
    env, _ = await _save(
        "knowledge",
        {
            "items": [
                {
                    "id": "k12",
                    "title": "12b",
                    "body": "سعر الجلسة ثمانون دولار مع تعليمات الحلاقة",
                    "status": "active",
                }
            ]
        },
        tid,
    )
    live = _published(tid)["knowledge"]["items"][0]
    assert live["title"] == "12b"
    assert live["ai_search_title"]
    assert live["ai_search_description"]
    titles = collect_operational_titles(_published(tid))
    row = next(item for item in titles if item.get("id") == "knowledge:k12")
    assert row["original_title"] == "12b"
    assert row["ai_search_title"]
    retrieval = await run_retrieval_luna(
        tenant_id=tid,
        message="قديش سعر الجلسة؟",
        customer_profile={},
        scripted_tool_calls=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": ["knowledge:k12"]}}],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["knowledge:k12"]}},
        ],
    )
    assert "ثمانون" in retrieval.evidence[0].content
    _fail_gen(SearchMetadata())
    with pytest.raises(MetadataPreparationError):
        await _save(
            "knowledge",
            {
                "items": [
                    {
                        "id": "k12",
                        "title": "12b",
                        "body": "سعر الجلسة تسعون ويجب ألا يصل للزبون",
                        "status": "active",
                    }
                ]
            },
            tid,
            etag=env.etag,
        )
    assert "ثمانون" in _published(tid)["knowledge"]["items"][0]["body"]
    assert "تسعون" not in _published(tid)["knowledge"]["items"][0]["body"]


@pytest.mark.asyncio
async def test_each_section_success_and_failure(v2_env) -> None:
    for section, payload in SECTION_CASES:
        tid = f"t_meta_sec_{section}"
        _ok_gen()
        env, first = await _save(section, payload, tid)
        key = _list_key(payload)
        live_rows = _published(tid)[section][key]
        item = live_rows[0]
        assert item.get("ai_search_title")
        assert item.get("ai_search_description")
        _fail_gen(SearchMetadata(title="Horaires d'ouverture", description="Contient les heures"))
        changed = dict(payload)
        changed[key] = [dict(payload[key][0])]
        if "body" in changed[key][0]:
            changed[key][0]["body"] = "must not go live"
        elif "notes" in changed[key][0]:
            changed[key][0]["notes"] = "must not go live"
        elif "ai_instructions" in changed[key][0]:
            changed[key][0]["ai_instructions"] = "must not go live"
        elif "en" in changed[key][0]:
            changed[key][0]["en"] = "must not go live"
        else:
            changed[key][0]["address"] = "must not go live"
        with pytest.raises(MetadataPreparationError):
            await _save(section, changed, tid, etag=env.etag)
        assert read_published_pointer(tid).content_version_id == first["content_version_id"]


@pytest.mark.asyncio
async def test_delete_goes_live_without_new_metadata(v2_env) -> None:
    tid = "t_meta_delete"
    env, _ = await _save(
        "knowledge",
        {
            "items": [
                {"id": "keep", "title": "keep", "body": "keep body", "status": "active"},
                {"id": "gone", "title": "gone", "body": "gone body", "status": "active"},
            ]
        },
        tid,
    )
    _fail_gen(SearchMetadata())
    envelope, activation = await _save(
        "knowledge",
        {"items": [{"id": "keep", "title": "keep", "body": "keep body", "status": "active"}]},
        tid,
        etag=env.etag,
    )
    assert activation.get("live") is True
    ids = {row["id"] for row in _published(tid)["knowledge"]["items"]}
    assert ids == {"keep"}
    assert envelope.payload["items"][0]["id"] == "keep"


def test_user_message_has_no_model_details() -> None:
    lowered = METADATA_PREPARATION_MESSAGE.lower()
    for token in ("luna", "terra", "openai", "gpt", "api key", "model"):
        assert token not in lowered
