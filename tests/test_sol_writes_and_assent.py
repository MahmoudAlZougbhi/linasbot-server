"""Sol writes always-on + Approve-bar-only confirm (no ok/موافق auto-approve)."""

from __future__ import annotations

from pathlib import Path

import pytest

from services.owner_copilot.flags import owner_copilot_shadow_planning, owner_copilot_writes_enabled


def test_writes_always_on_ignores_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OWNER_COPILOT_WRITES", "false")
    assert owner_copilot_writes_enabled() is True
    monkeypatch.delenv("OWNER_COPILOT_SHADOW_PLANNING", raising=False)
    assert owner_copilot_shadow_planning() is False


def test_no_assent_lexicon_auto_approve() -> None:
    assert not Path("services/owner_copilot/assent.py").exists()
    src = "\n".join(path.read_text(encoding="utf-8") for path in Path("services/owner_copilot").rglob("*.py"))
    assert "looks_like_owner_assent" not in src
    assert "resolve_pending_confirm_token" not in src
