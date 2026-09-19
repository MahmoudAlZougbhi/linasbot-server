"""Third-party comment joins: reply-to-page vs reply-to-human (Graph parent.from)."""

from __future__ import annotations

from unittest import mock

import pytest

from services.brain.comments.thread_parent import classify_comment_parent, skip_third_party_join
from services.brain.contracts.reply import FinalReplyEnvelope, OutboundMessage, TurnResult
from services.brain.contracts.turn import HistorySnapshot
from services.brain.conversation_store import reset_conversation_store_for_tests
from services.integrations.meta.meta_comment_events import ResolvedMetaCommentEvent, parse_meta_comment_events
from services.integrations.meta.meta_comment_replies import process_meta_comment_event
from tests.test_meta_comment_replies import _facebook_comment_payload, _settings
from tests.test_meta_comment_replies_more import MetaCommentProcessorTests


def test_classify_parent_edges() -> None:
    assert classify_comment_parent(parent_id="", post_id="p1") == "top_level"
    assert classify_comment_parent(parent_id="p1", post_id="p1") == "top_level"
    assert (
        classify_comment_parent(
            parent_id="ai-1",
            post_id="p1",
            parent_from_id="page",
            owner_ids={"page"},
        )
        == "page"
    )
    assert (
        classify_comment_parent(
            parent_id="ahmad-1",
            post_id="p1",
            parent_from_id="ahmad",
            owner_ids={"page"},
            current_author_id="omar",
        )
        == "human"
    )
    assert (
        classify_comment_parent(
            parent_id="ahmad-1",
            post_id="p1",
            parent_from_id="ahmad",
            owner_ids={"page"},
            current_author_id="ahmad",
        )
        == "same_author"
    )


def test_skip_human_thread_unless_all_comments(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "services.brain.comments.thread_parent.published_replies_to_any_comments",
        lambda *_a, **_k: False,
    )
    assert skip_third_party_join("human", tenant_id="t", channel="facebook", post_id="p1") is True
    assert skip_third_party_join("page", tenant_id="t", channel="facebook", post_id="p1") is False
    monkeypatch.setattr(
        "services.brain.comments.thread_parent.published_replies_to_any_comments",
        lambda *_a, **_k: True,
    )
    assert skip_third_party_join("human", tenant_id="t", channel="facebook", post_id="p1") is False


def _enabled_binding():
    helper = MetaCommentProcessorTests()
    helper.setUp()
    binding = helper._verified_binding()
    from services.integrations.meta.meta_comment_reply_settings import set_comment_reply_setting

    set_comment_reply_setting(
        tenant_id=binding.tenant_id,
        app_key=binding.app_key,
        channel=binding.channel,
        asset_id=binding.asset_id,
        enabled=True,
    )
    return helper, binding


@pytest.mark.asyncio
async def test_omar_reply_to_ahmad_is_ignored(monkeypatch: pytest.MonkeyPatch) -> None:
    helper, binding = _enabled_binding()
    try:
        payload = _facebook_comment_payload(author_id="omar")
        event = parse_meta_comment_events(payload, channel="facebook", page_id="111")[0]
        event["parent_id"] = "ahmad-comment"
        event["parent_from_id"] = "ahmad"
        event["post_id"] = "post-1"
        generate = mock.AsyncMock(return_value="ok")
        monkeypatch.setattr("services.integrations.meta.meta_comment_replies._generate_comment_reply_text", generate)
        result = await process_meta_comment_event(
            ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding),
            simulation=True,
        )
        assert result.status == "ignored"
        assert result.reason == "reply_to_human"
        generate.assert_not_called()
    finally:
        helper.tearDown()


@pytest.mark.asyncio
async def test_omar_reply_to_page_runs_under_omar_key(monkeypatch: pytest.MonkeyPatch) -> None:
    helper, binding = _enabled_binding()
    try:
        payload = _facebook_comment_payload(author_id="omar")
        event = parse_meta_comment_events(payload, channel="facebook", page_id="111")[0]
        event["parent_id"] = "page-reply-1"
        event["parent_from_id"] = "111"
        event["post_id"] = "post-1"
        generate = mock.AsyncMock(return_value="ok")
        monkeypatch.setattr("services.integrations.meta.meta_comment_replies._generate_comment_reply_text", generate)
        monkeypatch.setattr(
            "services.integrations.meta.meta_comment_replies._comment_has_page_reply",
            mock.AsyncMock(return_value=False),
        )
        result = await process_meta_comment_event(
            ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding),
            simulation=True,
        )
        assert result.status == "simulated"
        assert generate.await_args.kwargs["provider_sender_id"] == "omar"
        ctx = generate.await_args.kwargs["comment_context"]
        assert ctx["parent_is_page"] is True
    finally:
        helper.tearDown()


@pytest.mark.asyncio
async def test_ahmad_history_stays_on_ahmad_key(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_conversation_store_for_tests()
    seen: list[str] = []

    async def fake_history(**kwargs):
        seen.append(str(kwargs.get("conversation_id") or ""))
        return HistorySnapshot()

    monkeypatch.setattr("services.brain.runtime.load_history_snapshot", fake_history)
    monkeypatch.setattr("services.brain.runtime.winning_comment_mode", lambda **_k: (None, None))
    monkeypatch.setattr(
        "services.brain.runtime.evaluate_gates",
        lambda *_a, **_k: type("G", (), {"allow": True, "reason": "", "detail": {}})(),
    )
    monkeypatch.setattr("services.brain.runtime.apply_live_control", lambda turn: turn)

    async def fake_run(turn, *, message, channel):
        return TurnResult(
            stop_reason="ok",
            envelope=FinalReplyEnvelope(
                decision="reply",
                messages=[OutboundMessage(destination="comment", text="ok")],
            ),
        )

    monkeypatch.setattr("services.brain.runtime.run_dm_after_gates", fake_run)
    monkeypatch.setattr(
        "services.brain.comments.pipeline.apply_ai_comment_destinations",
        lambda result, _mode: result,
    )
    monkeypatch.setattr("services.brain.runtime.apply_message_billing", lambda _turn, result: result)

    from services.billing.entitlements_service import entitlements_store
    from services.brain.runtime import run_customer_ai_comment

    entitlements_store.set_plan(tenant_id="thread-shop", plan_id="starter", status="active", source="admin")
    await run_customer_ai_comment(
        tenant_id="thread-shop",
        comment_text="price?",
        post_id="p1",
        comment_id="c-ahmad-1",
        provider_sender_id="ahmad",
        channel="facebook_comment",
    )
    await run_customer_ai_comment(
        tenant_id="thread-shop",
        comment_text="and me?",
        post_id="p1",
        comment_id="c-omar-1",
        provider_sender_id="omar",
        channel="facebook_comment",
        parent_is_page=True,
        parent_comment="it's 90",
    )
    await run_customer_ai_comment(
        tenant_id="thread-shop",
        comment_text="ok book it",
        post_id="p1",
        comment_id="c-ahmad-2",
        provider_sender_id="ahmad",
        channel="facebook_comment",
        parent_is_page=True,
    )
    assert seen[0] == "comment:thread-shop:facebook_comment:p1:ahmad"
    assert seen[1] == "comment:thread-shop:facebook_comment:p1:omar"
    assert seen[2] == "comment:thread-shop:facebook_comment:p1:ahmad"
    assert seen[0] != seen[1]
