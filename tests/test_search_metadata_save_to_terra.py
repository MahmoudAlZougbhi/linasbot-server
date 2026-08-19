"""Full Save → Luna evidence → Terra prompt uses the live knowledge body."""

from __future__ import annotations

import json

import pytest

from services.cm.save_live import put_draft_and_go_live
from services.cm.storage import get_draft
from services.cm.version_store import load_published_content
from services.search_metadata.errors import MetadataPreparationError
from services.search_metadata.generate import SearchMetadata, reset_metadata_generator, set_metadata_generator

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def setup_function() -> None:
    set_metadata_generator(
        lambda _req: SearchMetadata(
            title="English Search Title",
            description="Contains the grounded item content for routing.",
        )
    )


def teardown_function() -> None:
    reset_metadata_generator()


async def _save(payload: dict, tenant_id: str, etag: str | None = None):
    match = etag
    if not match:
        env = get_draft("knowledge", tenant_id=tenant_id, create_default=True)
        match = env.etag
    return await put_draft_and_go_live(
        section="knowledge",
        payload=payload,
        if_match=match,
        tenant_id=tenant_id,
        updated_by="tester",
    )


def _live_body(tenant_id: str) -> str:
    _pointer, sections = load_published_content(tenant_id)
    return str(sections["knowledge"]["items"][0]["body"])


async def _terra_messages(tenant_id: str, message: str, item_id: str) -> str:
    from services.cm.version_store import read_published_pointer
    from services.customer_reply_v2.answer_luna import build_answer_messages
    from services.customer_reply_v2.manifest import load_fixed_answer_context
    from services.customer_reply_v2.retrieval_luna import run_retrieval_luna

    retrieval = await run_retrieval_luna(
        tenant_id=tenant_id,
        message=message,
        customer_profile={},
        scripted_tool_calls=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": [item_id]}}],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": [item_id]}},
        ],
    )
    pointer = read_published_pointer(tenant_id)
    assert pointer is not None
    fixed = load_fixed_answer_context(tenant_id)
    messages = build_answer_messages(
        message=message,
        fixed_context=fixed,
        evidence=list(retrieval.evidence),
        evidence_status=retrieval.evidence_status,
        customer_profile={},
        history_messages=[],
        comment_context=None,
        channel="instagram_dm",
        published_revision=pointer.content_version_id,
        response_language="ar",
        detected_language="ar",
    )
    return json.dumps(messages, ensure_ascii=False)


@pytest.mark.asyncio
async def test_save_success_terra_receives_new_knowledge_body(v2_env) -> None:
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    tid = "t_meta_terra_ok"
    env, _ = await _save(
        {"items": [{"id": "k1", "title": "12b", "body": "السعر القديم أربعون دولار", "status": "active"}]},
        tid,
    )
    await _save(
        {"items": [{"id": "k1", "title": "12b", "body": "السعر الجديد ثمانون دولار بعد التعديل", "status": "active"}]},
        tid,
        etag=env.etag,
    )
    assert "ثمانون" in _live_body(tid)
    blob = await _terra_messages(tid, "قديش سعر الجلسة؟", "knowledge:k1")
    assert "ثمانون دولار بعد التعديل" in blob
    assert "أربعون" not in blob
    assert "English Search Title" not in blob
    out = await run_customer_reply_v2_dm(
        tenant_id=tid,
        message="قديش سعر الجلسة؟",
        channel="instagram_dm",
        scripted_retrieval=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": ["knowledge:k1"]}}],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["knowledge:k1"]}},
        ],
        fixture_answer={
            "reply_text": "السعر الجديد ثمانون دولار بعد التعديل",
            "grounding_status": "grounded",
            "evidence_source_ids": ["knowledge:k1"],
        },
    )
    assert out.reply
    assert "ثمانون" in out.reply


@pytest.mark.asyncio
async def test_save_metadata_fail_terra_stays_on_old_body(v2_env) -> None:
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    tid = "t_meta_terra_fail"
    env, _ = await _save(
        {"items": [{"id": "k1", "title": "12b", "body": "السعر القديم أربعون دولار", "status": "active"}]},
        tid,
    )
    reset_metadata_generator()
    set_metadata_generator(lambda _req: SearchMetadata())
    with pytest.raises(MetadataPreparationError):
        await _save(
            {
                "items": [
                    {
                        "id": "k1",
                        "title": "12b",
                        "body": "السعر الجديد تسعون ويجب ألا يصل لتيرا",
                        "status": "active",
                    }
                ]
            },
            tid,
            etag=env.etag,
        )
    assert "أربعون" in _live_body(tid)
    assert "تسعون" not in _live_body(tid)
    blob = await _terra_messages(tid, "قديش سعر الجلسة؟", "knowledge:k1")
    assert "أربعون دولار" in blob
    assert "تسعون" not in blob
    out = await run_customer_reply_v2_dm(
        tenant_id=tid,
        message="قديش سعر الجلسة؟",
        channel="instagram_dm",
        scripted_retrieval=[
            [{"name": "read_published_cm_items", "arguments": {"item_ids": ["knowledge:k1"]}}],
            {"final_plan": {"evidence_status": "sufficient", "selected_source_ids": ["knowledge:k1"]}},
        ],
        fixture_answer={
            "reply_text": "السعر القديم أربعون دولار",
            "grounding_status": "grounded",
            "evidence_source_ids": ["knowledge:k1"],
        },
    )
    assert "أربعون" in (out.reply or "")
    assert "تسعون" not in (out.reply or "")
