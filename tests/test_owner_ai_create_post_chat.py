"""Create Post chat routing — owner tool + orchestrator intent."""

from __future__ import annotations

from typing import Any

import pytest

from services.owner_ai_model_router import classify_owner_route
from services.owner_ai_tools_creative import infer_creative_kind


def test_infer_creative_kind_auto_and_compress() -> None:
    assert infer_creative_kind("بدي نعمل بوست عن العرض", "auto") == "post"
    assert infer_creative_kind("please compress this caption", None) == "rewrite"
    assert infer_creative_kind("make an image for the sale", None) == "image"
    assert infer_creative_kind("anything", "compress") == "rewrite"


def test_creative_route_markers_include_arabic() -> None:
    assert classify_owner_route("بدي نعمل بوست") == "creative"
    assert classify_owner_route("write a caption for today") == "creative"
    assert classify_owner_route("hello", intent="create_creative_draft") == "creative"


def _stub_context(**_: Any) -> dict[str, Any]:
    return {
        "system_prompt": "x",
        "account_summary": {"setup_stage": "ready", "profile": {"preferred_language": "en"}},
        "knowledge_block": "",
        "capabilities": ["creative_studio"],
        "recent_messages": [],
        "conversation_summary": None,
        "reply_language": "en",
        "preferred_language": "en",
        "cm_full_dump": False,
        "full_history": False,
    }


@pytest.mark.asyncio
async def test_owner_turn_create_post_needs_brief(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_orchestrator import run_owner_turn
    from services.owner_ai_tools_base import ToolResult

    monkeypatch.setattr("services.owner_ai_orchestrator.pack_owner_turn_context", _stub_context)
    monkeypatch.setattr(
        "services.owner_ai_orchestrator.estimate_context_tokens",
        lambda _ctx: 10,
    )
    monkeypatch.setattr(
        "services.owner_ai_model_router.owner_chat_usage_tracker.record",
        lambda **_: {},
    )

    async def _fake_tool(name: str, **kwargs: Any) -> ToolResult:
        assert name == "create_creative_draft"
        return ToolResult(
            ok=True,
            name="create_creative_draft",
            data={
                "status": "needs_brief",
                "kind": "auto",
                "task_options": [{"id": "auto", "label": "Auto"}, {"id": "compress", "label": "Compress"}],
                "actions": {"publish": False, "edit": True, "regenerate": True, "schedule": True},
            },
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
    assert any(o.get("id") == "auto" for o in (turn.creative_draft.get("task_options") or []))
    assert "chat" in turn.reply_text.lower() or "بوست" in turn.reply_text or "الشات" in turn.reply_text


@pytest.mark.asyncio
async def test_owner_turn_create_post_generates_draft(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_orchestrator import run_owner_turn
    from services.owner_ai_tools_base import ToolResult

    monkeypatch.setattr("services.owner_ai_orchestrator.pack_owner_turn_context", _stub_context)
    monkeypatch.setattr(
        "services.owner_ai_orchestrator.estimate_context_tokens",
        lambda _ctx: 10,
    )
    monkeypatch.setattr(
        "services.owner_ai_model_router.owner_chat_usage_tracker.record",
        lambda **_: {},
    )

    async def _fake_tool(name: str, **kwargs: Any) -> ToolResult:
        assert name == "create_creative_draft"
        args = kwargs.get("args") or {}
        assert args.get("kind") == "post" or args.get("creative_kind") == "post"
        return ToolResult(
            ok=True,
            name="create_creative_draft",
            data={
                "status": "completed",
                "kind": "post",
                "text": "Summer sale starts Friday — book now.",
                "model": "test-model",
                "actions": {"publish": False, "edit": True, "regenerate": True, "schedule": True},
            },
        )

    monkeypatch.setattr("services.owner_ai_orchestrator.dispatch_tool", _fake_tool)

    turn = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="Create a post about our summer sale this Friday",
        tool_args={"creative_kind": "post"},
    )
    assert turn.route and turn.route.get("kind") == "creative"
    assert turn.creative_draft is not None
    assert turn.creative_draft.get("status") == "completed"
    assert "Summer sale" in (turn.creative_draft.get("text") or "")
    assert turn.creative_draft.get("actions", {}).get("publish") is False


@pytest.mark.asyncio
async def test_chip_kind_forces_create_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_orchestrator import run_owner_turn
    from services.owner_ai_tools_base import ToolResult

    monkeypatch.setattr("services.owner_ai_orchestrator.pack_owner_turn_context", _stub_context)
    monkeypatch.setattr(
        "services.owner_ai_orchestrator.estimate_context_tokens",
        lambda _ctx: 10,
    )
    monkeypatch.setattr(
        "services.owner_ai_model_router.owner_chat_usage_tracker.record",
        lambda **_: {},
    )

    seen: dict[str, Any] = {}

    async def _fake_tool(name: str, **kwargs: Any) -> ToolResult:
        seen["name"] = name
        seen["args"] = kwargs.get("args") or {}
        return ToolResult(
            ok=True,
            name="create_creative_draft",
            data={
                "status": "completed",
                "kind": "rewrite",
                "text": "Short sale note.",
                "actions": {"publish": False},
            },
        )

    monkeypatch.setattr("services.owner_ai_orchestrator.dispatch_tool", _fake_tool)

    turn = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="Our long announcement about prices and hours…",
        tool_args={"creative_kind": "compress"},
    )
    assert seen.get("name") == "create_creative_draft"
    assert seen.get("args", {}).get("kind") == "compress"
    assert turn.creative_draft and turn.creative_draft.get("kind") == "rewrite"
