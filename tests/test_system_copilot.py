"""System Copilot: knowledge registry, greeting, CM approval, gender, context compaction."""

from __future__ import annotations

from typing import Any

import pytest

from services.owner_ai_cm_approval import CmPatchProposalStore, approve_cm_patch, propose_cm_patch
from services.owner_ai_context import estimate_context_tokens, pack_owner_turn_context, summarize_conversation
from services.owner_ai_model_router import OwnerChatUsageTracker, classify_owner_route, route_owner_turn
from services.owner_ai_profile import address_line, never_infer_gender_from_identity, normalize_gender
from services.system_knowledge_registry import registry_route_errors, valid_mobile_routes
from services.system_knowledge_retrieval import retrieve_capabilities


def test_help_registry_routes_match_mobile_control_areas() -> None:
    errors = registry_route_errors()
    assert errors == []
    assert "cm" in valid_mobile_routes()
    assert "integrations" in valid_mobile_routes()


def test_targeted_retrieval_not_full_dump() -> None:
    caps = retrieve_capabilities("check my instagram connection", limit=3)
    assert 1 <= len(caps) <= 3
    assert any(c.feature == "integrations_meta" for c in caps)


def test_never_infer_gender_from_email_or_name() -> None:
    assert never_infer_gender_from_identity(email="sarah.jones@clinic.com", name="Sarah") == "unset"
    assert never_infer_gender_from_identity(email="mohammad@x.com", name="Mohammad") == "unset"
    assert normalize_gender(None) == "unset"
    assert normalize_gender("female") == "female"
    # Neutral address when unset
    line = address_line(
        {"display_name": "Alex", "gender": "unset", "form_of_address": ""},
        language="en",
    )
    assert line == "Hello Alex"
    assert "Mr" not in line and "Ms" not in line


def test_context_compaction_flags(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.owner_ai_context.build_account_summary",
        lambda **_: {
            "setup_stage": "new",
            "cm": {"sections_present": 0, "sections_total": 15, "published": False, "missing_sample": []},
            "integrations": {"any_connected": False},
            "plan": {"plan_id": "starter"},
            "wallet": {"balance": 0},
            "profile": {
                "display_name": "Alex",
                "gender": "unset",
                "preferred_language": "en",
                "form_of_address": None,
            },
        },
    )
    long_msgs = [{"role": "user", "content": f"msg {i} " * 40} for i in range(20)]
    ctx = pack_owner_turn_context(
        tenant_id="t1",
        user_id="u1",
        user_text="help me with usage",
        messages=long_msgs,
    )
    assert ctx["cm_full_dump"] is False
    assert ctx["full_history"] is False
    assert len(ctx["recent_messages"]) <= 8
    assert estimate_context_tokens(ctx) > 0
    summary = summarize_conversation(long_msgs)
    assert summary is not None


def test_model_router_and_usage_tracking(tmp_path: Any) -> None:
    assert classify_owner_route("show usage") == "owner_help"
    assert classify_owner_route("publish my content management draft") == "owner_complex_cm"
    decision = route_owner_turn("create a caption", intent=None)
    assert decision.kind in {"creative", "owner_help"}
    tracker = OwnerChatUsageTracker(root=tmp_path / "usage")
    tracker.record(
        tenant_id="t1",
        user_id="u1",
        conversation_id="c1",
        route=decision,
        prompt_tokens=120,
        completion_tokens=40,
    )
    totals = tracker.totals("t1")
    assert totals["turns"] == 1
    assert totals["total_tokens"] == 160


@pytest.mark.asyncio
async def test_cm_approval_flow(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    store = CmPatchProposalStore(root=tmp_path / "proposals")
    monkeypatch.setattr("services.owner_ai_cm_approval.cm_patch_proposal_store", store)

    preview = {
        "section": "style",
        "changed_keys": ["tone"],
        "current_sample": {"tone": ""},
        "proposed_sample": {"tone": "friendly"},
        "patch": {"tone": "friendly"},
        "revision": 1,
    }

    def _fake_preview(**kwargs: Any) -> dict[str, Any]:
        del kwargs
        return preview

    monkeypatch.setattr("services.owner_ai_cm_approval.build_patch_preview", _fake_preview)

    proposed = propose_cm_patch(
        tenant_id="t1",
        user_id="u1",
        section="style",
        patch={"tone": "friendly"},
    )
    assert proposed["requires_confirmation"] is True
    pid = proposed["proposal_id"]

    saved_calls: list[dict[str, Any]] = []

    def _fake_apply(**kwargs: Any) -> dict[str, Any]:
        saved_calls.append(kwargs)
        return {"section": "style", "revision": 2, "etag": "e2", "payload": {"tone": "friendly"}}

    monkeypatch.setattr("services.cm.setup_chat.apply_section_patch", _fake_apply)
    monkeypatch.setattr(
        "services.cm.validation.validate_cm",
        lambda **_: {"errors": [], "warnings": []},
    )
    monkeypatch.setattr(
        "services.faq_cm_invalidation.invalidate_faq_for_cm_patch",
        lambda **_: {"stale_groups": [], "stale_rows": 0, "reason": "cm_patch:style"},
    )

    # Without going through approve, draft is not saved
    assert saved_calls == []

    result = approve_cm_patch(tenant_id="t1", user_id="u1", proposal_id=pid, actor_id="u1")
    assert result["status"] == "approved"
    assert result["publish_prompt"] is False
    assert len(saved_calls) == 1
    assert saved_calls[0]["section"] == "style"


@pytest.mark.asyncio
async def test_owner_turn_help_and_publish_confirm(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_orchestrator import run_owner_turn

    monkeypatch.setattr(
        "services.owner_ai_context.pack_owner_turn_context",
        lambda **_: {
            "system_prompt": "x",
            "account_summary": {"setup_stage": "new", "profile": {"preferred_language": "en"}},
            "knowledge_block": "",
            "capabilities": ["system_copilot"],
            "recent_messages": [],
            "conversation_summary": None,
            "reply_language": "en",
            "preferred_language": "en",
            "cm_full_dump": False,
            "full_history": False,
        },
    )
    monkeypatch.setattr(
        "services.owner_ai_model_router.owner_chat_usage_tracker.record",
        lambda **_: {},
    )

    help_turn = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="what can you do",
    )
    assert (
        "System Copilot" in help_turn.reply_text
        or "capabilities" in help_turn.reply_text.lower()
        or help_turn.tool_calls
    )

    async def _publish(**kwargs: Any) -> Any:
        from services.owner_ai_tools_base import ToolResult

        del kwargs
        return ToolResult(
            ok=True,
            name="publish_cm",
            data={"action": "publish_cm"},
            requires_confirmation=True,
            confirmation_token="publish_cm",
            error="Confirmation required before publish",
        )

    monkeypatch.setattr("services.owner_ai_tools.dispatch_tool", _publish)
    pub = await run_owner_turn(
        tenant_id="t1",
        user_id="u1",
        role="admin",
        conversation_id="c1",
        user_text="publish",
    )
    assert pub.pending_confirmation == "publish_cm"


def test_greeting_stages(monkeypatch: pytest.MonkeyPatch) -> None:
    from services.owner_ai_greeting import build_greeting

    monkeypatch.setattr(
        "services.owner_ai_greeting.read_owner_profile",
        lambda _uid: {
            "display_name": None,
            "gender": "unset",
            "preferred_language": "en",
            "form_of_address": None,
            "address_prompt_asked": False,
        },
    )
    monkeypatch.setattr("services.owner_ai_greeting.resolve_setup_stage", lambda _tid: "new")
    g = build_greeting(tenant_id="t1", user_id="u1", language="en")
    assert "System Copilot" in g["text"]
    assert g["address_prompt_included"] is True
    assert g["gender"] == "unset"
