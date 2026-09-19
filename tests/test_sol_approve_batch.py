"""Pro before/after cards + multi pending + selective approve."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.owner_copilot.cards import card_from_tool
from services.owner_copilot.cm_approval import (
    CmPatchProposalStore,
    build_patch_preview,
    propose_cm_patch,
    reject_cm_patch,
)
from services.owner_copilot.cm_multi_approve import list_pending_cm_proposals, tool_approve_cm_batch


@pytest.fixture()
def tenant(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", Path(tmp_path))
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    store = CmPatchProposalStore(root=tmp_path / "props")
    monkeypatch.setattr("services.owner_copilot.cm_approval.cm_patch_proposal_store", store)
    return "tenant_sol_approve"


def test_preview_has_before_after_change_kind(tenant: str) -> None:
    preview = build_patch_preview(
        tenant_id=tenant,
        section="ai_basics",
        patch={"assistant_name": "Nour"},
    )
    assert preview["section"] == "ai_basics"
    assert preview["change_kind"] in {"add", "edit", "delete"}
    assert "before" in preview
    assert "after" in preview
    assert "Nour" in str(preview["after"])
    card = card_from_tool(
        "propose_cm_patch",
        {
            "proposal_id": "p1",
            "confirmation_token": "approve_cm_patch:p1",
            "preview": preview,
        },
        ok=True,
    )
    assert card is not None
    assert "Assent" not in card.body
    assert preview["change_kind"] in card.title or "ai_basics" in card.title.lower() or "assistant_name" in card.title


@pytest.mark.asyncio
async def test_multi_pending_selective_approve_keeps_siblings(tenant: str, monkeypatch: pytest.MonkeyPatch) -> None:
    a = propose_cm_patch(tenant_id=tenant, user_id="u1", section="ai_basics", patch={"assistant_name": "A"})
    b = propose_cm_patch(tenant_id=tenant, user_id="u1", section="style", patch={"tone": "warm"})
    pending = list_pending_cm_proposals(tenant_id=tenant, user_id="u1")
    assert {row["proposal_id"] for row in pending} == {a["proposal_id"], b["proposal_id"]}

    monkeypatch.setattr(
        "services.ai_setup.setup_chat.apply_section_patch",
        lambda **kwargs: {"revision": 1, "etag": "e", "section": kwargs.get("section")},
    )
    monkeypatch.setattr(
        "services.ai_setup.validation.validate_cm",
        lambda **_k: {"ok": True, "errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "services.ai_setup.faq_invalidation.invalidate_faq_for_cm_patch",
        lambda **_k: {},
    )

    async def _activate(**_k):
        return {"activated": True, "live": True}

    monkeypatch.setattr("services.owner_copilot.cm_approval.activate_cm_after_save", _activate)

    result = await tool_approve_cm_batch(
        tenant_id=tenant,
        user_id="u1",
        role="admin",
        proposal_ids=[a["proposal_id"]],
        confirmed=True,
    )
    assert result.ok is True
    leftover = list_pending_cm_proposals(tenant_id=tenant, user_id="u1")
    assert [row["proposal_id"] for row in leftover] == [b["proposal_id"]]
    reject_cm_patch(tenant_id=tenant, user_id="u1", proposal_id=b["proposal_id"])
    assert list_pending_cm_proposals(tenant_id=tenant, user_id="u1") == []
