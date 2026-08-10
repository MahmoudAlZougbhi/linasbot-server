"""Natural owner assent for pending Draft approvals (ok / موافق / yes)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.owner_ai_cm_approval import CmPatchProposalStore
from services.owner_copilot_v2.assent import (
    looks_like_owner_assent,
    pending_confirm_from_messages,
    resolve_pending_confirm_token,
)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("ok", True),
        ("OK", True),
        ("okay", True),
        ("yes", True),
        ("موافق", True),
        ("نعم", True),
        ("تمام", True),
        ("يلا", True),
        ("approve", True),
        ("Agree to save", True),
        ("ok please change the price to 50", False),
        ("لا", False),
        ("", False),
    ],
)
def test_looks_like_owner_assent(text: str, expected: bool) -> None:
    assert looks_like_owner_assent(text) is expected


def test_pending_confirm_from_messages_prefers_latest_token() -> None:
    messages = [
        {
            "role": "assistant",
            "content": "proposal ready",
            "tool_calls": [
                {
                    "ok": True,
                    "name": "propose_cm_patch",
                    "requires_confirmation": True,
                    "confirmation_token": "approve_cm_patch:old",
                    "data": {},
                }
            ],
        },
        {
            "role": "assistant",
            "content": "newer proposal",
            "tool_calls": [
                {
                    "ok": True,
                    "name": "propose_cm_patch",
                    "requires_confirmation": True,
                    "confirmation_token": "approve_cm_patch:new",
                    "data": {},
                }
            ],
        },
    ]
    assert pending_confirm_from_messages(messages) == "approve_cm_patch:new"


def test_resolve_pending_confirm_from_cm_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = CmPatchProposalStore(root=tmp_path / "props")
    monkeypatch.setattr("services.owner_ai_cm_approval.cm_patch_proposal_store", store)
    prop = store.create(
        tenant_id="t1",
        user_id="u1",
        section="ai_basics",
        patch={"welcome": "hi"},
        preview={"section": "ai_basics", "changed_keys": ["welcome"]},
    )
    token = resolve_pending_confirm_token(tenant_id="t1", user_id="u1", messages=[])
    assert token == f"approve_cm_patch:{prop.id}"


def test_system_prompt_mentions_natural_assent() -> None:
    from services.owner_copilot_v2.brain_support import SYSTEM_V2

    assert "ok" in SYSTEM_V2
    assert "موافق" in SYSTEM_V2
    assert "magic word" in SYSTEM_V2
