"""Approve Smart Answer must Activate FAQ Live (same path as CM #171)."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from services.owner_ai_tools_faq import (
    SmartAnswerProposalStore,
    tool_approve_smart_answer,
    tool_propose_smart_answer,
)


@pytest.fixture
def proposal_store(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> SmartAnswerProposalStore:
    store = SmartAnswerProposalStore(root=tmp_path / "smart_answers")
    monkeypatch.setattr("services.owner_ai_tools_faq.smart_answer_proposal_store", store)
    return store


@pytest.mark.asyncio
async def test_approve_smart_answer_activates_faq_live(
    proposal_store: SmartAnswerProposalStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "services.owner_ai_tools_faq.resolve_permissions",
        lambda _role, _tenant: {"contentManagers": True},
    )
    monkeypatch.setattr(
        "services.faq_entitlements.assert_can_create_faq",
        lambda _tid: {"faq_enabled": True},
    )
    create_faq_pair = AsyncMock(
        return_value={
            "success": True,
            "qa_group_id": "qa_test123",
            "detected_language": "en",
            "count_created": 4,
        }
    )
    activate = AsyncMock(
        return_value={
            "activated": True,
            "live": True,
            "mode": "section_overlay",
            "section": "faq",
            "content_version_id": "v1",
        }
    )
    monkeypatch.setattr("services.cm.faq_integration.create_faq_pair", create_faq_pair)
    monkeypatch.setattr("services.owner_ai_cm_approval.activate_cm_after_save", activate)

    proposed = await tool_propose_smart_answer(
        tenant_id="t1",
        role="owner",
        user_id="u1",
        question="What are your hours?",
        answer="We open 10 to 6.",
        language="en",
    )
    assert proposed.ok is True
    assert proposed.requires_confirmation is True
    proposal_id = str((proposed.data or {}).get("proposal_id") or "")
    assert proposal_id

    approved = await tool_approve_smart_answer(
        tenant_id="t1",
        role="owner",
        user_id="u1",
        proposal_id=proposal_id,
        confirmed=True,
    )
    assert approved.ok is True
    assert approved.data.get("qa_group_id") == "qa_test123"
    assert approved.data.get("live") is True
    assert (approved.data.get("activation") or {}).get("mode") == "section_overlay"
    create_faq_pair.assert_awaited_once()
    activate.assert_awaited_once()
    assert activate.await_args.kwargs.get("section") == "faq"

    stored = proposal_store.get(tenant_id="t1", proposal_id=proposal_id)
    assert stored is not None
    assert stored.status == "approved"


@pytest.mark.asyncio
async def test_propose_smart_answer_preview_explains_savings(
    proposal_store: SmartAnswerProposalStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del proposal_store
    monkeypatch.setattr(
        "services.owner_ai_tools_faq.resolve_permissions",
        lambda _role, _tenant: {"contentManagers": True},
    )
    monkeypatch.setattr(
        "services.faq_entitlements.assert_can_create_faq",
        lambda _tid: {"faq_enabled": True},
    )
    result = await tool_propose_smart_answer(
        tenant_id="t1",
        role="owner",
        user_id="u1",
        question="Hours?",
        answer="10-6",
        language="en",
    )
    preview = (result.data or {}).get("preview") or {}
    assert preview.get("section") == "faq"
    assert (
        "saving credits" in str(preview.get("impact") or "").lower()
        or "credits" in str(preview.get("impact") or "").lower()
    )
    assert "Hours?" in str(preview.get("proposed_value") or "")


def test_smart_answer_card_from_tool() -> None:
    from services.owner_copilot_v2.cards import card_from_tool

    card = card_from_tool(
        "propose_smart_answer",
        {
            "proposal_id": "p1",
            "confirmation_token": "approve_smart_answer:p1",
            "preview": {
                "section": "faq",
                "question": "Q?",
                "answer": "A.",
                "language": "en",
                "proposed_value": "Q (en): Q?\nA: A.",
            },
        },
        ok=True,
    )
    assert card is not None
    assert card.kind == "proposal"
    assert "Smart Answer" in card.title
    assert card.data.get("confirmation_token") == "approve_smart_answer:p1"
