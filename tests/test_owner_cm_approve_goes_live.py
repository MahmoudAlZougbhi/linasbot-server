"""Approve CM patch must publish Live so customer reply can read the change."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from services.owner_ai_cm_approval import (
    CmPatchProposalStore,
    activate_cm_after_save,
    approve_cm_patch_and_activate,
    propose_cm_patch,
)


@pytest.fixture
def proposal_store(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> CmPatchProposalStore:
    store = CmPatchProposalStore(root=tmp_path / "proposals")
    monkeypatch.setattr("services.owner_ai_cm_approval.cm_patch_proposal_store", store)
    return store


def _stub_approve_deps(monkeypatch: pytest.MonkeyPatch, *, section: str = "services") -> None:
    monkeypatch.setattr(
        "services.owner_ai_cm_approval.build_patch_preview",
        lambda **_: {
            "section": section,
            "changed_keys": ["sessions_note"],
            "current_sample": {"sessions_note": "7 sessions"},
            "proposed_sample": {"sessions_note": "7-10 sessions"},
            "current_value": "sessions_note:\n7 sessions",
            "proposed_value": "sessions_note:\n7-10 sessions",
            "patch": {"sessions_note": "7-10 sessions"},
            "revision": 1,
        },
    )
    monkeypatch.setattr(
        "services.cm.setup_chat.apply_section_patch",
        lambda **_: {"section": section, "revision": 2, "etag": "e2", "payload": {}},
    )
    monkeypatch.setattr(
        "services.cm.validation.validate_cm",
        lambda **_: {"ok": True, "errors": [], "warnings": [], "error_count": 0, "warning_count": 0},
    )
    monkeypatch.setattr(
        "services.faq_cm_invalidation.invalidate_faq_for_cm_patch",
        lambda **_: {"stale_groups": [], "stale_rows": 0, "reason": "none"},
    )


@pytest.mark.asyncio
async def test_activate_first_live_uses_full_publish_draft(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "services.cm.constants.tenant_has_published_cm",
        lambda _tid: False,
    )
    publish_draft = AsyncMock(
        return_value=type(
            "R",
            (),
            {"content_version_id": "v_first", "index_version_id": "idx_first"},
        )()
    )
    publish_sections = AsyncMock()
    monkeypatch.setattr("services.cm.publish.publish_draft", publish_draft)
    monkeypatch.setattr("services.cm.publish.publish_draft_sections", publish_sections)

    result = await activate_cm_after_save(tenant_id="t1", section="services", actor_id="u1")

    assert result["activated"] is True
    assert result["live"] is True
    assert result["mode"] == "first_live_full_publish"
    assert result["content_version_id"] == "v_first"
    publish_draft.assert_awaited_once()
    publish_sections.assert_not_awaited()
    assert "owner_ai_auto_activate_first_live:services" in str(publish_draft.await_args.kwargs.get("notes"))


@pytest.mark.asyncio
async def test_activate_with_published_base_uses_section_overlay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "services.cm.constants.tenant_has_published_cm",
        lambda _tid: True,
    )
    publish_draft = AsyncMock()
    publish_sections = AsyncMock(
        return_value=type(
            "R",
            (),
            {"content_version_id": "v_sec", "index_version_id": "idx_sec"},
        )()
    )
    monkeypatch.setattr("services.cm.publish.publish_draft", publish_draft)
    monkeypatch.setattr("services.cm.publish.publish_draft_sections", publish_sections)

    result = await activate_cm_after_save(tenant_id="t1", section="services", actor_id="u1")

    assert result["activated"] is True
    assert result["live"] is True
    assert result["mode"] == "section_overlay"
    publish_sections.assert_awaited_once()
    publish_draft.assert_not_awaited()
    assert publish_sections.await_args.kwargs["section_names"] == ["services"]


@pytest.mark.asyncio
async def test_activate_returns_publish_blocked_without_raising(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from services.cm.publish import PublishBlockedError

    monkeypatch.setattr(
        "services.cm.constants.tenant_has_published_cm",
        lambda _tid: False,
    )

    async def _blocked(**_kwargs: Any) -> Any:
        raise PublishBlockedError("blocked", errors=[{"code": "X"}])

    monkeypatch.setattr("services.cm.publish.publish_draft", _blocked)

    result = await activate_cm_after_save(tenant_id="t1", section="services", actor_id="u1")
    assert result["activated"] is False
    assert result["live"] is False
    assert result["reason"] == "publish_blocked"
    assert result["errors"] == [{"code": "X"}]


@pytest.mark.asyncio
async def test_approve_cm_patch_and_activate_sets_live(
    proposal_store: CmPatchProposalStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_approve_deps(monkeypatch)
    monkeypatch.setattr(
        "services.owner_ai_cm_approval.activate_cm_after_save",
        AsyncMock(
            return_value={
                "activated": True,
                "live": True,
                "mode": "first_live_full_publish",
                "section": "services",
                "content_version_id": "v1",
                "index_version_id": "i1",
            }
        ),
    )

    proposed = propose_cm_patch(
        tenant_id="t1",
        user_id="u1",
        section="services",
        patch={"sessions_note": "7-10 sessions"},
    )
    result = await approve_cm_patch_and_activate(
        tenant_id="t1",
        user_id="u1",
        proposal_id=proposed["proposal_id"],
        actor_id="u1",
    )

    assert result["status"] == "approved"
    assert result["live"] is True
    assert result["activation"]["activated"] is True
    assert result["publish_prompt"] is False
    assert proposal_store.get(tenant_id="t1", proposal_id=proposed["proposal_id"]).status == "approved"


@pytest.mark.asyncio
async def test_tool_approve_cm_patch_returns_live_activation(
    proposal_store: CmPatchProposalStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _stub_approve_deps(monkeypatch)
    monkeypatch.setattr(
        "services.owner_ai_cm_approval.activate_cm_after_save",
        AsyncMock(
            return_value={
                "activated": True,
                "live": True,
                "mode": "section_overlay",
                "section": "services",
                "content_version_id": "v2",
                "index_version_id": "i2",
            }
        ),
    )
    proposed = propose_cm_patch(
        tenant_id="t1",
        user_id="u1",
        section="services",
        patch={"sessions_note": "7-10 sessions"},
    )
    from services.owner_ai_tools_write import tool_approve_cm_patch

    result = await tool_approve_cm_patch(
        tenant_id="t1",
        role="admin",
        user_id="u1",
        proposal_id=proposed["proposal_id"],
        confirmed=True,
    )
    assert result.ok is True
    assert result.data["live"] is True
    assert result.data["activation"]["live"] is True
