"""Customer AI V10 Phase 5 — Comment Rule engine."""

from __future__ import annotations

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def _section(**kwargs):
    payload = {
        "default_action": "reply_comment",
        "policy_text": "",
        "rules": [],
    }
    payload.update(kwargs)
    return payload


def test_normalize_arabic_and_punctuation() -> None:
    from services.customer_reply_v2.comment_text_norm import normalize_comment_text

    assert normalize_comment_text("  PRICE!! ") == "price"
    assert normalize_comment_text("مُهتم") == normalize_comment_text("مهتم")


def test_legacy_ignore_and_template_migrate() -> None:
    from services.customer_reply_v2.comment_rule_migrate import migrate_comment_rule

    ignore, note = migrate_comment_rule({"id": "r1", "action": "ignore", "keywords": ["spam"]})
    assert ignore["id"] == "r1"
    assert ignore["rule_mode"] == "deterministic"
    assert ignore["static_action"] == "ignore"
    assert "deterministic" in note

    templated, _ = migrate_comment_rule(
        {"id": "r2", "action": "reply_dm", "reply_template": "hi", "keywords": ["price"]}
    )
    assert templated["rule_mode"] == "deterministic"
    assert templated["static_action"] == "send_dm_static"

    ai, _ = migrate_comment_rule({"id": "r3", "action": "reply_comment", "keywords": ["size"]})
    assert ai["rule_mode"] == "ai_guidance"


def test_global_keyword_static_dm_and_specific_override() -> None:
    from services.customer_reply_v2.comment_rule_engine import evaluate_comment_engine

    section = _section(
        rules=[
            {
                "id": "global",
                "enabled": True,
                "keywords": ["price"],
                "action": "reply_dm",
                "reply_template": "global dm",
                "priority": 1,
            },
            {
                "id": "post",
                "enabled": True,
                "keywords": ["price"],
                "action": "reply_dm",
                "reply_template": "post dm",
                "post_id": "POST_A",
                "priority": 1,
            },
        ]
    )
    global_hit = evaluate_comment_engine(section, comment_text="what is the PRICE?", post_id="OTHER")
    assert global_hit.rule_id == "global"
    assert global_hit.rule_mode == "deterministic"
    assert global_hit.action == "send_dm_static"
    specific = evaluate_comment_engine(section, comment_text="price", post_id="POST_A")
    assert specific.rule_id == "post"
    assert specific.scope == "specific_post"


def test_priority_and_ignore_and_all_comments() -> None:
    from services.customer_reply_v2.comment_rule_engine import evaluate_comment_engine

    section = _section(
        rules=[
            {
                "id": "low",
                "enabled": True,
                "keywords": ["hello"],
                "action": "reply_comment",
                "reply_template": "low",
                "priority": 1,
            },
            {
                "id": "high",
                "enabled": True,
                "keywords": ["hello"],
                "action": "ignore",
                "priority": 50,
            },
        ]
    )
    hit = evaluate_comment_engine(section, comment_text="hello there")
    assert hit.rule_id == "high"
    assert hit.action == "ignore"

    all_rules = _section(
        rules=[
            {
                "id": "all",
                "enabled": True,
                "trigger_type": "all_comments",
                "rule_mode": "deterministic",
                "static_action": "reply_comment_static",
                "reply_template": "thanks",
                "priority": 1,
            }
        ]
    )
    thanks = evaluate_comment_engine(all_rules, comment_text="anything at all")
    assert thanks.rule_id == "all"
    assert thanks.trigger_matched == "all_comments"


def test_inactive_deleted_and_other_post_do_not_apply() -> None:
    from services.customer_reply_v2.comment_rule_engine import evaluate_comment_engine

    section = _section(
        rules=[
            {"id": "off", "enabled": False, "keywords": ["x"], "action": "ignore"},
            {"id": "gone", "status": "deleted", "keywords": ["x"], "action": "ignore"},
            {"id": "other", "post_id": "P1", "keywords": ["x"], "action": "ignore"},
        ]
    )
    miss = evaluate_comment_engine(section, comment_text="x please", post_id="P2")
    assert miss.matched is False


def test_ai_guidance_conflict_keeps_higher_priority() -> None:
    from services.customer_reply_v2.comment_rule_engine import evaluate_comment_engine

    section = _section(
        rules=[
            {
                "id": "g1",
                "keywords": ["size"],
                "action": "reply_comment",
                "priority": 1,
                "ai_action_mode": "reply_comment",
                "ai_instructions": "be brief",
            },
            {
                "id": "g2",
                "keywords": ["size"],
                "action": "reply_dm",
                "priority": 9,
                "ai_action_mode": "send_dm",
                "ai_instructions": "ask for DM details",
            },
        ]
    )
    hit = evaluate_comment_engine(section, comment_text="what size?")
    assert hit.rule_mode == "ai_guidance"
    assert hit.rule_id == "g2"
    assert hit.conflict_event == "ai_action_conflict"
    assert len(hit.ai_guidance_rules) == 1


def test_other_tenant_account_rejected() -> None:
    from services.customer_reply_v2.connected_posts import account_belongs_to_tenant

    assert account_belongs_to_tenant(tenant_id="no-such", platform="instagram", connected_account_id="x") is False


@pytest.mark.asyncio
async def test_deterministic_comment_rule_skips_ai(v2_env) -> None:
    sections = _rich_sections()
    sections["comments"] = {
        "default_action": "reply_comment",
        "rules": [
            {
                "id": "kw",
                "enabled": True,
                "name": "Price DM",
                "keywords": ["price"],
                "action": "reply_dm",
                "reply_template": "Sent you the details privately.",
            }
        ],
    }
    await publish_test_content("t_crule", sections)
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    out = await run_customer_reply_v2_comment(
        tenant_id="t_crule",
        comment_text="price please",
        detected_language="en",
        response_language="en",
        channel="instagram_comment",
        post_id="POST1",
        comment_id="C1",
        scripted_retrieval=[{"final_plan": {"evidence_status": "sufficient", "selected_source_ids": []}}],
        fixture_answer={"reply_text": "AI SHOULD NOT RUN", "grounding_status": "grounded"},
    )
    assert out.reason == "comment_rule_deterministic"
    assert "privately" in (out.reply or "")
    assert out.metadata.get("ai_called") is False
    ops = [row["operation"] for row in (out.metadata.get("metering") or {}).get("invocations") or []]
    assert "comment_rule_deterministic" in ops
    assert "luna_retrieval" not in ops


@pytest.mark.asyncio
async def test_ai_guidance_blocks_faq_direct(v2_env) -> None:
    sections = _rich_sections()
    sections["comments"] = {
        "rules": [
            {
                "id": "guide",
                "enabled": True,
                "keywords": ["أوقات"],
                "action": "reply_comment",
                "ai_instructions": "Keep public replies short.",
            }
        ]
    }
    await publish_test_content("t_guide", sections)
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    out = await run_customer_reply_v2_comment(
        tenant_id="t_guide",
        comment_text="شو أوقاتكم؟",
        detected_language="ar",
        response_language="ar",
        channel="instagram_comment",
        scripted_retrieval=[{"final_plan": {"evidence_status": "insufficient_final", "selected_source_ids": []}}],
        fixture_answer={"reply_text": "AI hours reply", "grounding_status": "grounded"},
    )
    assert out.metadata.get("faq_direct_reply") is not True
    assert out.reason != "faq_direct"
    assert out.metadata.get("comment_rule_mode") == "ai_guidance"


def test_capability_denied_has_diagnostic() -> None:
    from services.customer_reply_v2.comment_rule_engine import CommentEngineResult
    from services.customer_reply_v2.comment_rule_runtime import deterministic_rule_outcome
    from services.customer_reply_v2.invocation_meter import CustomerTurnMeter

    engine = CommentEngineResult(
        matched=True,
        rule_mode="deterministic",
        rule_id="r",
        action="send_dm_static",
        dm_text="hi",
    )
    out = deterministic_rule_outcome(
        engine=engine,
        meter=CustomerTurnMeter(tenant_id="t"),
        channel_meta={"channel_capabilities": {"can_send_dm": False, "can_reply_publicly": True}},
    )
    assert out.reason == "comment_rule_capability_denied"
    assert out.metadata.get("owner_diagnostic") == "channel_cannot_send_dm"
    assert out.metadata.get("ai_called") is False
