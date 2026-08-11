"""Setup AI chat writes the same CM draft SoT as manual forms."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.cm.setup_chat import apply_section_patch, interpret_and_patch, start_setup
from services.cm.storage import get_draft, put_draft


@pytest.fixture()
def tenant_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("TOKEN_WALLET_UNLIMITED_TENANT_IDS", "setup-tenant")
    from storage import persistent_storage as ps

    monkeypatch.setattr(ps, "_DATA_ROOT", tmp_path)
    monkeypatch.setattr(ps, "_LINASBOT_DATA_ROOT", str(tmp_path))
    return tmp_path


@pytest.mark.asyncio
async def test_setup_chat_patch_updates_same_draft(tenant_root: Path) -> None:
    start = start_setup("setup-tenant", "user-1")
    assert "إعداد" in start["intro"] or "AI Setup" in start["intro"]

    result = await interpret_and_patch(
        tenant_id="setup-tenant",
        user_id="user-1",
        message="My gym is Iron Peak and the assistant is Coach Bot",
        actor_id="user-1",
        section="ai_basics",
        use_llm=False,
    )
    assert result["section"] == "ai_basics"
    draft = get_draft("ai_basics", tenant_id="setup-tenant", create_default=False)
    assert "Iron Peak" in str(draft.payload.get("clinic_name") or "")
    assert draft.payload == result["saved"]["payload"]


def test_setup_chat_rejects_forbidden_fields(tenant_root: Path) -> None:
    with pytest.raises(ValueError, match="Forbidden"):
        apply_section_patch(
            tenant_id="setup-tenant",
            section="ai_basics",
            patch={"tenant_id": "evil", "assistant_name": "X"},
            actor_id="user-1",
        )


def test_manual_and_setup_share_draft_store(tenant_root: Path) -> None:
    apply_section_patch(
        tenant_id="setup-tenant",
        section="style",
        patch={"tone": "friendly"},
        actor_id="setup",
    )
    env = get_draft("style", tenant_id="setup-tenant", create_default=True)
    assert env.payload.get("tone") == "friendly"
    updated = put_draft(
        "style",
        payload={**dict(env.payload), "formality": "casual"},
        if_match=env.etag,
        updated_by="manual-ui",
        tenant_id="setup-tenant",
    )
    assert updated.payload.get("tone") == "friendly"
    assert updated.payload.get("formality") == "casual"
