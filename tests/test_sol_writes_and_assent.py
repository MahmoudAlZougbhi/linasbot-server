"""Sol writes always-on + Approve-bar-only confirm (no ok/موافق auto-approve)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.owner_copilot.assent import resolve_pending_confirm_token
from services.owner_copilot.flags import owner_copilot_shadow_planning, owner_copilot_writes_enabled


def test_writes_always_on_ignores_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_COPILOT_WRITES", "false")
    assert owner_copilot_writes_enabled() is True
    monkeypatch.delenv("OWNER_COPILOT_SHADOW_PLANNING", raising=False)
    assert owner_copilot_shadow_planning() is False


def test_no_assent_lexicon_auto_approve() -> None:
    src = Path("services/owner_copilot/assent.py").read_text(encoding="utf-8")
    assert "looks_like_owner_assent" not in src
    assert "ok/موافق" in src or "ok / موافق" in src
    assert "never" in src.lower() or "never" in src
    # resolve_pending_confirm_token is unused on the live path; freeze no keyword matcher.
    assert "def looks_like" not in src


def test_resolve_pending_does_not_inspect_ok_text(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_copilot.cm_approval import CmPatchProposalStore

    store = CmPatchProposalStore(root=tmp_path / "props")
    monkeypatch.setattr("services.owner_copilot.cm_approval.cm_patch_proposal_store", store)
    token = resolve_pending_confirm_token(
        tenant_id="t1",
        user_id="u1",
        messages=[{"role": "user", "content": "ok موافق yes"}],
    )
    assert token is None
