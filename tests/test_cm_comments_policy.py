"""CM Comments section: schema, rule evaluation, no DM→public fallback."""

from __future__ import annotations

from services.cm.comment_rules import evaluate_comment_rules
from services.cm.constants import CM_SECTIONS
from services.cm.schemas import CommentRule, CommentsSection, default_section_payload


def test_comments_in_cm_sections() -> None:
    assert "comments" in CM_SECTIONS
    assert CM_SECTIONS.index("comments") == CM_SECTIONS.index("actions") + 1


def test_comments_default_payload() -> None:
    section = CommentsSection.model_validate(default_section_payload("comments"))
    assert section.rules == []
    assert section.default_action == "reply_comment"
    assert section.policy_text == ""


def test_keyword_rule_ignore() -> None:
    section = CommentsSection(
        rules=[
            CommentRule(
                id="r1",
                name="spam",
                keywords=["spam", "buy followers"],
                action="ignore",
            )
        ]
    )
    decision = evaluate_comment_rules(section, comment_text="Please buy followers now")
    assert decision.matched is True
    assert decision.action == "ignore"
    assert decision.rule_id == "r1"


def test_reply_dm_requires_template_text_in_decision() -> None:
    section = CommentsSection(
        rules=[
            CommentRule(
                id="r2",
                keywords=["book", "حجز"],
                action="reply_dm",
                reply_template="Hi — message us your preferred time.",
            )
        ]
    )
    decision = evaluate_comment_rules(section, comment_text="Can I book tomorrow?")
    assert decision.action == "reply_dm"
    assert "preferred time" in decision.reply_text


def test_post_id_scoping() -> None:
    section = CommentsSection(
        rules=[
            CommentRule(
                id="r3",
                keywords=["price"],
                action="ignore",
                post_id="POST_A",
            )
        ]
    )
    miss = evaluate_comment_rules(section, comment_text="price please", post_id="POST_B")
    assert miss.matched is False
    assert miss.action == "reply_comment"
    hit = evaluate_comment_rules(section, comment_text="price please", post_id="POST_A")
    assert hit.matched is True
    assert hit.action == "ignore"


def test_fixed_public_reply_template() -> None:
    section = CommentsSection(
        rules=[
            CommentRule(
                id="r4",
                keywords=["hours"],
                action="reply_comment",
                reply_template="We are open 10–8 daily.",
            )
        ]
    )
    decision = evaluate_comment_rules(section, comment_text="What are your hours?")
    assert decision.action == "reply_comment"
    assert decision.reply_text.startswith("We are open")


def test_default_ignore() -> None:
    section = CommentsSection(default_action="ignore", policy_text="Be brief")
    decision = evaluate_comment_rules(section, comment_text="hello")
    assert decision.matched is False
    assert decision.action == "ignore"
    assert decision.policy_text == "Be brief"
