"""Comment automatic vs AI, platform isolation, and thread identity."""

from __future__ import annotations

from services.customer_reply_v2.comment_rule_engine import evaluate_comment_engine
from services.customer_reply_v2.history_format import comment_thread_records


def _section(rules: list[dict]) -> dict:
    return {"default_action": "reply_comment", "policy_text": "", "rules": rules}


def test_automatic_keyword_does_not_need_luna() -> None:
    result = evaluate_comment_engine(
        _section(
            [
                {
                    "id": "auto",
                    "enabled": True,
                    "keywords": ["price"],
                    "action": "reply_comment",
                    "reply_template": "See our menu",
                    "rule_mode": "deterministic",
                    "channel": "facebook",
                    "post_id": "POST_FB",
                    "scope": "specific_post",
                }
            ]
        ),
        comment_text="what is the PRICE?",
        channel="facebook_comment",
        post_id="POST_FB",
    )
    assert result.matched is True
    assert result.rule_mode == "deterministic"
    assert result.reply_text == "See our menu"


def test_instagram_rule_does_not_leak_to_facebook() -> None:
    section = _section(
        [
            {
                "id": "ig",
                "enabled": True,
                "keywords": ["hello"],
                "action": "reply_comment",
                "reply_template": "ig only",
                "rule_mode": "deterministic",
                "channel": "instagram",
                "platform": "instagram",
                "post_id": "POST_IG",
                "scope": "specific_post",
            }
        ]
    )
    ig = evaluate_comment_engine(section, comment_text="hello", channel="instagram_comment", post_id="POST_IG")
    fb = evaluate_comment_engine(section, comment_text="hello", channel="facebook_comment", post_id="POST_IG")
    assert ig.rule_id == "ig"
    assert fb.matched is False


def test_mohamad_is_third_party_not_ahmad_history() -> None:
    records = comment_thread_records(
        channel="instagram_comment",
        comment_text="عندكم أزرق؟",
        parent_comment="Do you have Nivea?",
        comment_id="c-mohamad-1",
        post_id="POST",
        current_author_id="mohamad",
        current_author_name="Mohamad",
        parent_author_id="ahmad",
        parent_author_name="Ahmad",
        nearby_reply_records=[
            {
                "text": "Yes, Nivea Soft is in stock.",
                "author_id": "page",
                "author_name": "Linas",
                "from_page": True,
                "comment_id": "c-ai-1",
            },
            {
                "text": "and the price?",
                "author_id": "ahmad",
                "author_name": "Ahmad",
                "from_page": False,
                "comment_id": "c-ahmad-2",
            },
        ],
    )
    blob = " ".join(str(r.get("text") or r.get("content") or "") for r in records)
    assert "other_participant" in blob
    assert "Ahmad" in blob
    assert records[-1].get("message_id") == "c-mohamad-1"
    assert "current_author" in blob or records[-1].get("author_id") == "mohamad"


def test_ahmad_returns_after_third_party_keeps_his_identity() -> None:
    records = comment_thread_records(
        channel="instagram_comment",
        comment_text="رجعت، بدي السعر",
        comment_id="c-ahmad-3",
        current_author_id="ahmad",
        current_author_name="Ahmad",
        nearby_reply_records=[
            {
                "text": "عندكم أزرق؟",
                "author_id": "mohamad",
                "author_name": "Mohamad",
                "from_page": False,
                "comment_id": "c-mohamad-1",
            }
        ],
    )
    blob = " ".join(str(r.get("text") or "") for r in records)
    assert "other_participant" in blob
    assert "Mohamad" in blob
    assert records[-1].get("message_id") == "c-ahmad-3"


def test_facebook_rule_does_not_leak_to_instagram() -> None:
    section = _section(
        [
            {
                "id": "fb",
                "enabled": True,
                "keywords": ["hello"],
                "action": "reply_comment",
                "reply_template": "fb only",
                "rule_mode": "deterministic",
                "channel": "facebook",
                "platform": "facebook",
                "post_id": "POST_FB",
                "scope": "specific_post",
            }
        ]
    )
    fb = evaluate_comment_engine(section, comment_text="hello", channel="facebook_comment", post_id="POST_FB")
    ig = evaluate_comment_engine(section, comment_text="hello", channel="instagram_comment", post_id="POST_FB")
    assert fb.rule_id == "fb"
    assert ig.matched is False


def test_specific_ai_beats_global_automatic() -> None:
    result = evaluate_comment_engine(
        _section(
            [
                {
                    "id": "global-auto",
                    "enabled": True,
                    "keywords": ["size"],
                    "action": "reply_comment",
                    "reply_template": "global",
                    "rule_mode": "deterministic",
                    "channel": "any",
                    "scope": "all_posts",
                    "priority": 9,
                },
                {
                    "id": "post-ai",
                    "enabled": True,
                    "keywords": ["size"],
                    "rule_mode": "ai_guidance",
                    "ai_instructions": "Answer from catalog",
                    "channel": "instagram",
                    "platform": "instagram",
                    "post_id": "POST_IG",
                    "scope": "specific_post",
                    "priority": 1,
                },
            ]
        ),
        comment_text="size?",
        channel="instagram_comment",
        post_id="POST_IG",
    )
    assert result.rule_mode == "ai_guidance"
    assert result.rule_id == "post-ai"
    assert result.ai_guidance_rules[0]["id"] == "post-ai"


def test_other_post_ai_rule_does_not_enter() -> None:
    result = evaluate_comment_engine(
        _section(
            [
                {
                    "id": "other-post",
                    "enabled": True,
                    "keywords": ["hi"],
                    "rule_mode": "ai_guidance",
                    "post_id": "POST_OTHER",
                    "scope": "specific_post",
                    "channel": "instagram",
                },
                {
                    "id": "this-post",
                    "enabled": True,
                    "keywords": ["hi"],
                    "rule_mode": "ai_guidance",
                    "post_id": "POST_THIS",
                    "scope": "specific_post",
                    "channel": "instagram",
                    "ai_instructions": "this post only",
                },
            ]
        ),
        comment_text="hi",
        channel="instagram_comment",
        post_id="POST_THIS",
    )
    ids = [row["id"] for row in result.ai_guidance_rules]
    assert ids == ["this-post"]


def test_thread_labels_same_author_vs_third_party() -> None:
    records = comment_thread_records(
        channel="instagram_comment",
        comment_text="and the price?",
        parent_comment="Do you have Nivea?",
        comment_id="c-ahmad-2",
        post_id="POST",
        current_author_id="ahmad",
        current_author_name="Ahmad",
        parent_author_id="ahmad",
        parent_author_name="Ahmad",
        nearby_reply_records=[
            {
                "text": "Yes, Nivea Soft is in stock.",
                "author_id": "page",
                "author_name": "Linas",
                "from_page": True,
                "comment_id": "c-ai-1",
            },
            {
                "text": "I want the blue one",
                "author_id": "mohamad",
                "author_name": "Mohamad",
                "from_page": False,
                "comment_id": "c-mohamad-1",
            },
        ],
    )
    blob = " ".join(str(r.get("text") or r.get("content") or "") for r in records)
    assert "same_author" in blob or "current_author" in blob
    assert "other_participant" in blob
    assert "Mohamad" in blob
    assert records[-1].get("message_id") == "c-ahmad-2"


def test_reply_to_ai_keeps_comment_id_target() -> None:
    records = comment_thread_records(
        channel="facebook_comment",
        comment_text="thanks",
        comment_id="c-reply",
        current_author_id="u1",
        current_author_name="Ahmad",
        nearby_reply_records=[{"text": "hello", "author_id": "page", "from_page": True, "comment_id": "c-ai"}],
    )
    assert records[-1]["message_id"] == "c-reply"
    assert any("page_reply" in str(r.get("text") or "") for r in records)


def test_precedence_matrix_specific_beats_global() -> None:
    section = _section(
        [
            {
                "id": "global-ai",
                "enabled": True,
                "keywords": ["hi"],
                "rule_mode": "ai_guidance",
                "ai_instructions": "global ai",
                "channel": "any",
                "scope": "all_posts",
                "priority": 9,
            },
            {
                "id": "global-auto",
                "enabled": True,
                "keywords": ["hi"],
                "rule_mode": "deterministic",
                "reply_template": "global auto",
                "channel": "any",
                "scope": "all_posts",
                "priority": 8,
            },
            {
                "id": "ig-post-ai",
                "enabled": True,
                "keywords": ["hi"],
                "rule_mode": "ai_guidance",
                "ai_instructions": "ig post ai",
                "channel": "instagram",
                "platform": "instagram",
                "post_id": "POST_IG",
                "scope": "specific_post",
                "priority": 1,
            },
            {
                "id": "ig-post-auto",
                "enabled": True,
                "keywords": ["hi"],
                "rule_mode": "deterministic",
                "reply_template": "ig post auto",
                "channel": "instagram",
                "platform": "instagram",
                "post_id": "POST_IG",
                "scope": "specific_post",
                "priority": 1,
            },
        ]
    )
    specific_auto = evaluate_comment_engine(section, comment_text="hi", channel="instagram_comment", post_id="POST_IG")
    assert specific_auto.rule_mode == "deterministic"
    assert specific_auto.rule_id == "ig-post-auto"

    no_auto = _section([row for row in section["rules"] if row["id"] != "ig-post-auto"])
    specific_ai = evaluate_comment_engine(no_auto, comment_text="hi", channel="instagram_comment", post_id="POST_IG")
    assert specific_ai.rule_mode == "ai_guidance"
    assert specific_ai.rule_id == "ig-post-ai"

    fb = evaluate_comment_engine(section, comment_text="hi", channel="facebook_comment", post_id="POST_IG")
    assert fb.rule_id not in {"ig-post-auto", "ig-post-ai"}

    other_post = evaluate_comment_engine(section, comment_text="hi", channel="instagram_comment", post_id="POST_OTHER")
    assert other_post.rule_id not in {"ig-post-auto", "ig-post-ai"}
