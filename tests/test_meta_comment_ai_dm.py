"""Meta comment ai_dm reaches Brain; static DM stays on the template path."""

from __future__ import annotations

from unittest import mock

import pytest

from services.cm.comment_rules import CommentRuleDecision
from services.customer_ai.comments.destinations import CommentDestinations
from services.meta_comment_events import ResolvedMetaCommentEvent, parse_meta_comment_events
from services.meta_comment_reply_settings import set_comment_reply_setting
from services.meta_comment_rule_modes import (
    allows_private_after_public_reply,
    is_static_both_comment,
    is_static_comment_dm,
    is_static_public_comment,
    static_dm_text,
)
from tests.test_meta_comment_replies import _binding, _facebook_comment_payload, _settings
from tests.test_meta_comment_replies_more import MetaCommentProcessorTests


def test_comment_rule_mode_gates() -> None:
    ai_dm = CommentRuleDecision(action="reply_dm", rule_mode="ai_dm", matched=True)
    static_dm = CommentRuleDecision(
        action="reply_dm",
        rule_mode="static_dm",
        matched=True,
        dm_text="Book via DM",
    )
    leftover = CommentRuleDecision(
        action="reply_comment",
        rule_mode="ai_comment",
        matched=True,
        reply_text="leftover template",
    )
    both = CommentRuleDecision(action="reply_comment_and_dm", rule_mode="static_both", matched=True)
    assert is_static_comment_dm(ai_dm) is False
    assert is_static_comment_dm(static_dm) is True
    assert allows_private_after_public_reply(ai_dm) is True
    assert allows_private_after_public_reply(leftover) is False
    assert is_static_public_comment(leftover) is False
    assert is_static_both_comment(both) is True
    assert static_dm_text(static_dm) == "Book via DM"


@pytest.mark.asyncio
async def test_ai_dm_calls_generate(tmp_path, monkeypatch) -> None:
    from services.meta_comment_replies import process_meta_comment_event

    helper = MetaCommentProcessorTests()
    helper.setUp()
    try:
        binding = helper._verified_binding()
        set_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
            enabled=True,
        )
        monkeypatch.setattr("services.cm.constants.tenant_uses_cm_runtime", lambda _t: True)
        monkeypatch.setattr(
            "services.cm.comment_rules.evaluate_published_comment_rules",
            lambda *a, **k: CommentRuleDecision(
                action="reply_dm",
                rule_mode="ai_dm",
                matched=True,
                rule_id="ai-dm-1",
            ),
        )
        generate = mock.AsyncMock(
            return_value=CommentDestinations(private_text="Hours are 9-5", comment_mode="ai_dm")
        )
        monkeypatch.setattr("services.meta_comment_replies._generate_comment_reply_text", generate)
        monkeypatch.setattr(
            "services.meta_comment_replies._comment_has_page_reply",
            mock.AsyncMock(return_value=True),
        )
        event = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")[0]
        sent: list[dict] = []
        result = await process_meta_comment_event(
            ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding),
            simulation=True,
            capture_send=sent,
        )
        generate.assert_awaited_once()
        assert result.status in {"simulated", "simulated_dm", "simulated_both"}
        assert sent and sent[0]["delivery"] == "private_reply"
        assert sent[0]["message"] == "Hours are 9-5"
    finally:
        helper.tearDown()


@pytest.mark.asyncio
async def test_static_dm_uses_template_not_brain(monkeypatch) -> None:
    from services.meta_comment_replies import process_meta_comment_event

    helper = MetaCommentProcessorTests()
    helper.setUp()
    try:
        binding = helper._verified_binding()
        set_comment_reply_setting(
            tenant_id=binding.tenant_id,
            app_key=binding.app_key,
            channel=binding.channel,
            asset_id=binding.asset_id,
            enabled=True,
        )
        monkeypatch.setattr("services.cm.constants.tenant_uses_cm_runtime", lambda _t: True)
        monkeypatch.setattr(
            "services.cm.comment_rules.evaluate_published_comment_rules",
            lambda *a, **k: CommentRuleDecision(
                action="reply_dm",
                rule_mode="static_dm",
                matched=True,
                rule_id="st-dm",
                dm_text="Message us to book.",
            ),
        )
        generate = mock.AsyncMock(return_value="should-not-run")
        monkeypatch.setattr("services.meta_comment_replies._generate_comment_reply_text", generate)
        monkeypatch.setattr(
            "services.meta_comment_replies._comment_has_page_reply",
            mock.AsyncMock(return_value=False),
        )
        event = parse_meta_comment_events(_facebook_comment_payload(), channel="facebook", page_id="111")[0]
        sent: list[dict] = []
        result = await process_meta_comment_event(
            ResolvedMetaCommentEvent(event=event, settings=_settings(binding), binding=binding),
            simulation=True,
            capture_send=sent,
        )
        generate.assert_not_called()
        assert result.status == "simulated"
        assert sent[0]["message"] == "Message us to book."
    finally:
        helper.tearDown()


def test_meta_ingress_source_routes_ai_dm() -> None:
    from inspect import getsource

    from services.meta_comment_replies import process_meta_comment_event

    src = getsource(process_meta_comment_event)
    assert "is_static_comment_dm" in src
    assert "allows_private_after_public_reply" in src
    assert "comment_rule_dm_template_required" not in src
    assert "is_static_public_comment" in src

