"""Tests for Owner Copilot CM soft-delete propose → Approve→Live bar."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.cm.storage import ensure_defaults, get_draft, put_draft
from services.owner_ai_cm_approval import CmPatchProposalStore, approve_cm_patch
from services.owner_ai_tools_cm_delete import tool_propose_cm_delete
from services.owner_copilot_v2.brain_support import SYSTEM_V2
from services.owner_copilot_v2.cards import card_from_tool
from services.owner_copilot_v2.tool_schemas import tool_names


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return tmp_path


def _seed_faq(tenant_id: str = "t1") -> None:
    ensure_defaults(tenant_id=tenant_id)
    env = get_draft("faq", tenant_id=tenant_id)
    put_draft(
        "faq",
        payload={
            "items": [
                {
                    "qa_group_id": "qa_a",
                    "variants": [
                        {
                            "language": "en",
                            "question": "Hours?",
                            "answer": "9-5",
                            "reviewed": True,
                            "is_auto_translated": False,
                        }
                    ],
                    "tags": [],
                    "notes": None,
                    "status": "active",
                    "source_language": "en",
                    "reviewed": True,
                    "provenance": "test",
                    "revision": 1,
                },
                {
                    "qa_group_id": "qa_b",
                    "variants": [
                        {
                            "language": "en",
                            "question": "Price?",
                            "answer": "10$",
                            "reviewed": True,
                            "is_auto_translated": False,
                        }
                    ],
                    "tags": [],
                    "notes": None,
                    "status": "active",
                    "source_language": "en",
                    "reviewed": True,
                    "provenance": "test",
                    "revision": 1,
                },
            ],
            "notes": None,
        },
        if_match=env.etag,
        tenant_id=tenant_id,
        updated_by="tester",
    )


@pytest.mark.asyncio
async def test_propose_cm_delete_faq_archives_on_approve(
    tenant_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del tenant_root
    _seed_faq()
    store = CmPatchProposalStore(root=tmp_path / "del_proposals")
    monkeypatch.setattr("services.owner_ai_cm_approval.cm_patch_proposal_store", store)
    monkeypatch.setattr(
        "services.cm.validation.validate_cm",
        lambda **_: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "services.faq_cm_invalidation.invalidate_faq_for_cm_patch",
        lambda **_: {"stale_groups": [], "stale_rows": 0, "reason": "cm_patch:faq"},
    )

    proposed = await tool_propose_cm_delete(
        tenant_id="t1",
        role="admin",
        user_id="u1",
        section="faq",
        item_ids=["qa_a", "qa_b"],
    )
    assert proposed.ok is True
    assert proposed.requires_confirmation is True
    preview = proposed.data["preview"]
    assert preview["kind"] == "cm_delete"
    assert len(preview["targets"]) == 2
    titles = {t["title"] for t in preview["targets"]}
    assert "Hours?" in titles and "Price?" in titles

    card = card_from_tool("propose_cm_delete", proposed.data, ok=True)
    assert card is not None
    assert card.kind == "proposal"
    assert "Hours?" in (card.body or "")

    approve_cm_patch(
        tenant_id="t1",
        user_id="u1",
        proposal_id=proposed.data["proposal_id"],
        actor_id="u1",
        delete_ids=["qa_a"],
    )
    after = get_draft("faq", tenant_id="t1")
    by_id = {row["qa_group_id"]: row for row in (after.payload.get("items") or [])}
    assert by_id["qa_a"]["status"] == "archived"
    assert by_id["qa_b"]["status"] == "active"


@pytest.mark.asyncio
async def test_propose_cm_delete_ai_basics_clears_fields(
    tenant_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    del tenant_root
    ensure_defaults(tenant_id="t1")
    env = get_draft("ai_basics", tenant_id="t1")
    put_draft(
        "ai_basics",
        payload={
            **env.payload,
            "assistant_name": "Lina",
            "clinic_name": "Demo Clinic",
            "short_introduction": "Hello",
        },
        if_match=env.etag,
        tenant_id="t1",
        updated_by="tester",
    )
    store = CmPatchProposalStore(root=tmp_path / "del_basics")
    monkeypatch.setattr("services.owner_ai_cm_approval.cm_patch_proposal_store", store)
    monkeypatch.setattr(
        "services.cm.validation.validate_cm",
        lambda **_: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "services.faq_cm_invalidation.invalidate_faq_for_cm_patch",
        lambda **_: {"stale_groups": [], "stale_rows": 0, "reason": "cm_patch:ai_basics"},
    )

    proposed = await tool_propose_cm_delete(
        tenant_id="t1",
        role="admin",
        user_id="u1",
        section="ai_basics",
        delete_all=True,
    )
    assert proposed.ok is True
    assert proposed.data["preview"]["kind"] == "cm_delete"
    assert len(proposed.data["preview"]["targets"]) >= 3

    approve_cm_patch(
        tenant_id="t1",
        user_id="u1",
        proposal_id=proposed.data["proposal_id"],
        actor_id="u1",
    )
    after = get_draft("ai_basics", tenant_id="t1")
    assert after.payload.get("assistant_name") == ""
    assert after.payload.get("clinic_name") == ""


def test_system_v2_teaches_immediate_bar_and_delete() -> None:
    assert "propose_cm_delete" in SYSTEM_V2
    assert "Do NOT ask" in SYSTEM_V2
    assert "Approve | Cancel | Edit" in SYSTEM_V2
    assert "propose_cm_delete" in tool_names()
