"""System Copilot V2: creative cancelled under OWNER_COPILOT_V2."""

from __future__ import annotations

from typing import Any

import pytest


def _stub_context(**_: Any) -> dict[str, Any]:
    return {
        "system_prompt": "x",
        "account_summary": {"setup_stage": "ready", "profile": {"preferred_language": "en"}},
        "knowledge_block": "",
        "capabilities": ["system_copilot"],
        "recent_messages": [],
        "conversation_summary": None,
        "reply_language": "en",
        "preferred_language": "en",
        "cm_full_dump": False,
        "full_history": False,
    }


@pytest.mark.asyncio
async def test_v2_creative_request_refused_no_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_orchestrator import run_owner_turn

    monkeypatch.setenv("OWNER_COPILOT_V2", "true")
    monkeypatch.setattr("services.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: False)
    monkeypatch.setattr("services.owner_ai_context.pack_owner_turn_context", _stub_context)

    turn = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="I want to create a post with an image",
    )
    assert turn.creative_draft is None
    assert "DMs and comments" in turn.reply_text or "comments" in turn.reply_text.lower()
    assert turn.route and turn.route.get("reason") == "creative_cancelled"


@pytest.mark.asyncio
async def test_legacy_create_post_still_reachable_when_v2_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Dormant path: only when OWNER_COPILOT_V2=false (not offered in product UI)."""
    from services.owner_ai_orchestrator import run_owner_turn
    from services.owner_ai_tools_base import ToolResult

    monkeypatch.setenv("OWNER_COPILOT_V2", "false")
    monkeypatch.setattr("services.credit_ai_gate.ai_generation_blocked", lambda *_a, **_k: False)
    monkeypatch.setattr("services.owner_ai_orchestrator.pack_owner_turn_context", _stub_context)
    monkeypatch.setattr("services.owner_ai_orchestrator.estimate_context_tokens", lambda _ctx: 10)
    monkeypatch.setattr("services.owner_ai_model_router.owner_chat_usage_tracker.record", lambda **_: {})

    async def _fake_tool(name: str, **kwargs: Any) -> ToolResult:
        assert name == "create_creative_draft"
        return ToolResult(
            ok=True,
            name="create_creative_draft",
            data={"status": "needs_brief", "kind": "auto", "task_options": [{"id": "auto", "label": "Auto"}]},
        )

    monkeypatch.setattr("services.owner_ai_orchestrator.dispatch_tool", _fake_tool)
    turn = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="بدي نعمل بوست",
    )
    assert turn.creative_draft is not None
    assert turn.creative_draft.get("status") == "needs_brief"
