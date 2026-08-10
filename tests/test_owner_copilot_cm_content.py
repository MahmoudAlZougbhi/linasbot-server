"""Owner Copilot CM article/FAQ full read + surgical upsert tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.cm.storage import ensure_defaults, get_draft, put_draft
from services.owner_ai_cm_approval import CmPatchProposalStore, approve_cm_patch
from services.owner_ai_tools_cm_content import (
    tool_list_cm_articles,
    tool_list_cm_faq,
    tool_propose_cm_article_upsert,
    tool_propose_cm_faq_upsert,
    tool_read_cm_article,
    tool_read_cm_faq,
)
from services.owner_ai_tools_read import tool_read_cm
from services.owner_copilot_v2.tool_schemas import tool_names


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return tmp_path


def _seed_knowledge(tenant_id: str = "t1") -> None:
    ensure_defaults(tenant_id=tenant_id)
    env = get_draft("knowledge", tenant_id=tenant_id)
    long_body = "A" * 7000 + "TAIL"
    put_draft(
        "knowledge",
        payload={
            "items": [
                {
                    "id": "art_short",
                    "title": "Hours note",
                    "body": "We open at 9.",
                    "tags": ["hours"],
                    "language": "en",
                    "audience": "general",
                    "category": "",
                    "status": "active",
                    "source_filename": "hours.json",
                    "source_checksum": None,
                    "linked_service_ids": [],
                    "linked_branch_ids": [],
                    "notes": None,
                },
                {
                    "id": "art_long",
                    "title": "Long file",
                    "body": long_body,
                    "tags": [],
                    "language": "en",
                    "audience": "general",
                    "category": "",
                    "status": "active",
                    "source_filename": "long.json",
                    "source_checksum": None,
                    "linked_service_ids": [],
                    "linked_branch_ids": [],
                    "notes": None,
                },
            ],
            "notes": None,
        },
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by="tester",
    )


@pytest.mark.asyncio
async def test_list_and_read_cm_articles_with_chunking(tenant_root: Path) -> None:
    del tenant_root
    _seed_knowledge()

    listed = await tool_list_cm_articles(tenant_id="t1", role="admin", section="knowledge")
    assert listed.ok is True
    assert listed.data["total"] == 2
    ids = {a["id"] for a in listed.data["articles"]}
    assert ids == {"art_short", "art_long"}
    assert all("body" not in a for a in listed.data["articles"])

    short = await tool_read_cm_article(tenant_id="t1", role="admin", section="knowledge", article_id="art_short")
    assert short.ok is True
    assert short.data["article"]["body"] == "We open at 9."
    assert short.data["article"]["body_complete"] is True

    first = await tool_read_cm_article(
        tenant_id="t1",
        role="admin",
        section="knowledge",
        article_id="art_long",
        body_offset=0,
        body_limit=6000,
    )
    assert first.ok is True
    assert first.data["article"]["body_complete"] is False
    assert first.data["article"]["body_next_offset"] == 6000
    assert len(first.data["article"]["body"]) == 6000

    rest = await tool_read_cm_article(
        tenant_id="t1",
        role="admin",
        section="knowledge",
        article_id="art_long",
        body_offset=6000,
        body_limit=6000,
    )
    assert rest.ok is True
    assert rest.data["article"]["body"].endswith("TAIL")
    assert rest.data["article"]["body_complete"] is True


@pytest.mark.asyncio
async def test_propose_cm_article_upsert_then_approve(
    tenant_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    del tenant_root
    _seed_knowledge()
    store = CmPatchProposalStore(root=tmp_path / "proposals")
    monkeypatch.setattr("services.owner_ai_cm_approval.cm_patch_proposal_store", store)

    proposed = await tool_propose_cm_article_upsert(
        tenant_id="t1",
        role="admin",
        user_id="u1",
        section="knowledge",
        article={"id": "art_short", "title": "Hours note", "body": "We open at 10."},
    )
    assert proposed.ok is True
    assert proposed.requires_confirmation is True
    assert proposed.data["action"] == "update"
    pid = proposed.data["proposal_id"]

    monkeypatch.setattr(
        "services.cm.validation.validate_cm",
        lambda **_: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "services.faq_cm_invalidation.invalidate_faq_for_cm_patch",
        lambda **_: {"stale_groups": [], "stale_rows": 0, "reason": "cm_patch:knowledge"},
    )

    result = approve_cm_patch(tenant_id="t1", user_id="u1", proposal_id=pid, actor_id="u1")
    assert result["status"] == "approved"

    env = get_draft("knowledge", tenant_id="t1")
    items = env.payload.get("items") or []
    match = next(i for i in items if i["id"] == "art_short")
    assert match["body"] == "We open at 10."
    assert len(items) == 2


@pytest.mark.asyncio
async def test_faq_list_read_and_upsert(tenant_root: Path, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    del tenant_root
    ensure_defaults(tenant_id="t1")
    env = get_draft("faq", tenant_id="t1")
    put_draft(
        "faq",
        payload={
            "items": [
                {
                    "qa_group_id": "qa_demo",
                    "variants": [
                        {
                            "language": "en",
                            "question": "Price?",
                            "answer": "10$",
                            "reviewed": False,
                            "is_auto_translated": False,
                        },
                        {
                            "language": "ar",
                            "question": "السعر؟",
                            "answer": "10$",
                            "reviewed": False,
                            "is_auto_translated": False,
                        },
                    ],
                    "tags": [],
                    "notes": None,
                    "status": "active",
                    "source_language": "en",
                    "reviewed": True,
                    "provenance": "test",
                    "revision": 1,
                }
            ],
            "notes": None,
        },
        if_match=env.etag,
        tenant_id="t1",
        updated_by="tester",
    )

    listed = await tool_list_cm_faq(tenant_id="t1", role="admin")
    assert listed.ok is True
    assert listed.data["total"] == 1
    assert listed.data["items"][0]["qa_group_id"] == "qa_demo"

    read = await tool_read_cm_faq(tenant_id="t1", role="admin", qa_group_id="qa_demo")
    assert read.ok is True
    assert len(read.data["item"]["variants"]) == 2

    store = CmPatchProposalStore(root=tmp_path / "faq_proposals")
    monkeypatch.setattr("services.owner_ai_cm_approval.cm_patch_proposal_store", store)
    monkeypatch.setattr(
        "services.cm.validation.validate_cm",
        lambda **_: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "services.faq_cm_invalidation.invalidate_faq_for_cm_patch",
        lambda **_: {"stale_groups": [], "stale_rows": 0, "reason": "cm_patch:faq"},
    )

    proposed = await tool_propose_cm_faq_upsert(
        tenant_id="t1",
        role="admin",
        user_id="u1",
        faq={
            "qa_group_id": "qa_demo",
            "status": "archived",
            "variants": [
                {
                    "language": "en",
                    "question": "Price?",
                    "answer": "12$",
                    "reviewed": True,
                    "is_auto_translated": False,
                },
            ],
        },
    )
    assert proposed.ok is True
    approve_cm_patch(tenant_id="t1", user_id="u1", proposal_id=proposed.data["proposal_id"], actor_id="u1")
    after = get_draft("faq", tenant_id="t1")
    item = (after.payload.get("items") or [])[0]
    assert item["status"] == "archived"
    assert item["variants"][0]["answer"] == "12$"


@pytest.mark.asyncio
async def test_read_cm_small_section_returns_full_payload(tenant_root: Path) -> None:
    del tenant_root
    ensure_defaults(tenant_id="t1")
    env = get_draft("ai_basics", tenant_id="t1")
    put_draft(
        "ai_basics",
        payload={
            **env.payload,
            "assistant_name": "Lina",
            "clinic_name": "Demo",
            "short_introduction": "Hello",
        },
        if_match=env.etag,
        tenant_id="t1",
        updated_by="tester",
    )
    result = await tool_read_cm(tenant_id="t1", role="admin", section="ai_basics")
    assert result.ok is True
    draft = result.data["draft"]
    assert draft.get("payload_complete") is True
    assert draft["payload"]["assistant_name"] == "Lina"


def test_v2_schemas_include_cm_content_tools() -> None:
    names = tool_names()
    for required in (
        "list_cm_articles",
        "read_cm_article",
        "list_cm_faq",
        "read_cm_faq",
        "propose_cm_article_upsert",
        "propose_cm_faq_upsert",
    ):
        assert required in names
