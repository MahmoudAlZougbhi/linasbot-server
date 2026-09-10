"""Phase 0/1 Customer Brain contracts, history, flags, and comment aliases."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from services.cm.comment_rules import evaluate_comment_rules
from services.cm.schemas import CommentRule, CommentsSection
from services.customer_ai.comment_normalize import normalize_comment_mode
from services.customer_ai.contracts.reply import FinalReplyEnvelope, OutboundMessage
from services.customer_ai.contracts.turn import CustomerTurn
from services.customer_ai.flags import customer_brain_enabled
from services.customer_ai.history import build_history_snapshot
from services.customer_ai.precedence import wins
from services.customer_ai.providers.spaces import ENTITY_DOCUMENT, ENTITY_QUERY, KNOWLEDGE_DOCUMENT, compatible
from services.customer_ai.search.readiness import search_readiness
from services.customer_reply_v2.models import ENGINE_REMOVED
from services.customer_reply_v2.orchestrator import run_customer_reply_v2_comment, run_customer_reply_v2_dm


def test_brain_flag_defaults_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_BRAIN_ENABLED", raising=False)
    assert customer_brain_enabled() is False


def test_customer_turn_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        CustomerTurn(tenant_id="t1", extra_model_grant="evil")  # type: ignore[call-arg]


def test_legacy_reply_text_is_projection() -> None:
    envelope = FinalReplyEnvelope(
        decision="reply",
        messages=[
            OutboundMessage(destination="comment", text="public"),
            OutboundMessage(destination="dm", text="private"),
        ],
    )
    assert envelope.public_comment_text == "public"
    assert envelope.private_dm_text == "private"
    assert envelope.reply_text == "public"


def test_history_keeps_all_17_and_marks_inbound_once() -> None:
    raw = [{"id": f"m{i}", "role": "user" if i % 2 == 0 else "assistant", "text": str(i)} for i in range(17)]
    snap = build_history_snapshot(raw, current_inbound_id="m16", current_inbound_text="16")
    assert len(snap.messages) == 17
    assert [item.id for item in snap.messages] == [f"m{i}" for i in range(17)]
    assert sum(1 for item in snap.messages if item.is_current_inbound) == 1
    assert snap.messages[-1].id == "m16"


def test_history_caps_80_to_latest_50_without_duplicate_inbound() -> None:
    raw = [{"id": f"m{i}", "role": "user", "text": str(i)} for i in range(80)]
    snap = build_history_snapshot(raw, current_inbound_id="m79", current_inbound_text="79")
    assert len(snap.messages) == 50
    assert snap.messages[0].id == "m30"
    assert snap.messages[-1].id == "m79"
    assert snap.truncated_to_cap is True
    assert sum(1 for item in snap.messages if item.is_current_inbound) == 1


def test_history_excludes_private_notes_and_other_kinds() -> None:
    raw = [
        {"id": "u1", "role": "user", "text": "hi"},
        {"id": "note", "role": "staff_note", "text": "private"},
        {"id": "draft", "role": "assistant", "text": "unsent", "unsent": True},
        {"id": "staff", "role": "staff", "text": "we will help"},
        {"id": "evt", "role": "user", "kind": "internal_event", "text": "trace"},
    ]
    snap = build_history_snapshot(raw, current_inbound_id="u1")
    assert [item.id for item in snap.messages] == ["u1", "staff"]


def test_comment_alias_normalization() -> None:
    assert normalize_comment_mode(action="ignore") == "ignore"
    assert normalize_comment_mode(action="reply_comment_static") == "static_comment"
    assert normalize_comment_mode(action="send_dm_static") == "static_dm"
    assert normalize_comment_mode(action="reply_comment_and_dm_static") == "static_both"
    assert (
        normalize_comment_mode(action="reply_comment", rule_mode="ai_guidance", ai_action_mode="send_dm")
        == "ai_dm"
    )
    assert normalize_comment_mode(action="unknown_thing") is None


def test_comment_priority_and_all_comments() -> None:
    section = CommentsSection(
        rules=[
            CommentRule(
                id="low",
                keywords=["price"],
                action="reply_comment",
                reply_template="low",
                priority=1,
            ),
            CommentRule(
                id="high",
                keywords=["price"],
                action="ignore",
                priority=5,
            ),
        ]
    )
    decision = evaluate_comment_rules(section, comment_text="price please")
    assert decision.rule_id == "high"
    assert decision.action == "ignore"

    all_comments = CommentsSection(
        rules=[
            CommentRule(
                id="all",
                trigger_type="all_comments",
                action="ignore",
                keywords=[],
            )
        ]
    )
    hit = evaluate_comment_rules(all_comments, comment_text="anything at all")
    assert hit.matched is True
    assert hit.rule_id == "all"


def test_specific_post_beats_all_posts() -> None:
    section = CommentsSection(
        rules=[
            CommentRule(id="global", keywords=["sale"], action="reply_comment", reply_template="g", priority=9),
            CommentRule(
                id="post",
                keywords=["sale"],
                action="ignore",
                scope="specific_post",
                post_id="P1",
                priority=0,
            ),
        ]
    )
    hit = evaluate_comment_rules(section, comment_text="sale?", post_id="P1")
    assert hit.rule_id == "post"


def test_human_control_outranks_faq() -> None:
    assert wins("human_control", "faq_fast_path") == "human_control"


def test_spaces_same_dimension_are_not_compatible() -> None:
    assert compatible(ENTITY_DOCUMENT, ENTITY_QUERY) is True
    assert compatible(KNOWLEDGE_DOCUMENT, ENTITY_QUERY) is False


def test_search_readiness_without_voyage_is_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VOYAGE_API_KEY", "")
    status = search_readiness()
    assert status.ready is False
    assert status.reason == "provider_not_configured"


@pytest.mark.asyncio
async def test_facade_flag_off_still_engine_removed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CUSTOMER_BRAIN_ENABLED", raising=False)
    out = await run_customer_reply_v2_dm(tenant_id="t1", message="hello")
    assert out.reason == ENGINE_REMOVED
    assert out.metadata.get("ai_called") is False
    comment = await run_customer_reply_v2_comment(tenant_id="t1", comment_text="nice")
    assert comment.reason == ENGINE_REMOVED
