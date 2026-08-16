"""Customer AI V10 Phase 8 — FAQ resources + Comments regressions."""

from __future__ import annotations

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


def _hours_with_resource() -> dict:
    sections = _rich_sections()
    sections["faq"]["items"][0]["attachments"] = [
        {
            "id": "cmed_hours_poster",
            "kind": "image",
            "title": "Hours poster",
            "description": "Photo of opening hours",
            "status": "active",
        }
    ]
    return sections


async def _install_hours_faq(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_tier(message: str, _lang: str):
        if "hours" in message.lower():
            return {
                "tier": "exact",
                "match_score": 1.0,
                "matched_language": "en",
                "qa_pair": {
                    "id": "faq_hours",
                    "qa_group_id": "faq_hours",
                    "revision": "7",
                    "question": "What are your hours?",
                    "answer": "We open 10am to 6pm.",
                    "language": "en",
                },
            }
        return None

    monkeypatch.setattr("services.local_qa_service.local_qa_service.find_match_with_tier", _fake_tier)


@pytest.mark.asyncio
async def test_exact_faq_without_resources_still_direct(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    await publish_test_content("t_faq_plain", _rich_sections())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_plain",
        message="What are your hours?",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
    )
    assert hit.hit is True
    assert hit.reason in {"faq_exact", "exact", "faq_direct"}


@pytest.mark.asyncio
async def test_exact_faq_with_resource_is_not_text_only_direct(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    await publish_test_content("t_faq_res", _hours_with_resource())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_res",
        message="What are your hours?",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
    )
    assert hit.hit is False
    assert hit.reason == "faq_needs_resource"


@pytest.mark.asyncio
async def test_mixed_faq_still_skips_direct(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    await publish_test_content("t_faq_mix_res", _rich_sections())
    await _install_hours_faq(monkeypatch)
    from services.customer_reply_v2.faq_fast_path import try_faq_fast_path

    hit = await try_faq_fast_path(
        tenant_id="t_faq_mix_res",
        message="What are your hours and ابعتلي صور?",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
    )
    assert hit.hit is False
    assert hit.reason in {"mixed_intent", "partial_coverage"}


def test_replace_faq_attachments_requires_title_and_description(v2_env) -> None:
    from services.cm.faq_integration_helpers import FAQ_SECTION, FaqIntegrationError
    from services.cm.faq_integration_ops import replace_cm_faq_attachments
    from services.cm.storage import get_draft, put_draft

    env = get_draft(FAQ_SECTION, tenant_id="t_faq_put", create_default=True)
    put_draft(
        FAQ_SECTION,
        payload={"items": [{"qa_group_id": "faq_1", "status": "draft", "variants": []}]},
        if_match=env.etag,
        tenant_id="t_faq_put",
    )
    with pytest.raises(FaqIntegrationError):
        replace_cm_faq_attachments(
            qa_group_id="faq_1",
            attachments=[{"id": "cmed_x", "kind": "image", "title": "", "description": "d"}],
            tenant_id="t_faq_put",
        )
    out = replace_cm_faq_attachments(
        qa_group_id="faq_1",
        attachments=[
            {
                "id": "cmed_ok",
                "kind": "image",
                "title": "Hours poster",
                "description": "Photo of opening hours",
            }
        ],
        tenant_id="t_faq_put",
    )
    assert out["success"] is True
    assert out["data"]["attachments"][0]["title"] == "Hours poster"


def test_ai_guidance_does_not_static_send_resources() -> None:
    from services.customer_reply_v2.comment_rule_engine import evaluate_comment_engine

    engine = evaluate_comment_engine(
        {
            "rules": [
                {
                    "id": "rule_guide",
                    "enabled": True,
                    "rule_mode": "ai_guidance",
                    "trigger_type": "contains_any",
                    "keywords": ["price"],
                    "ai_action_mode": "reply_comment",
                    "ai_instructions": "Be polite. Use published knowledge.",
                    "attachments": [
                        {
                            "id": "cmed_guide",
                            "kind": "image",
                            "title": "Not a knowledge substitute",
                            "description": "Must not static-send",
                            "status": "active",
                        }
                    ],
                }
            ]
        },
        comment_text="price please",
        channel="instagram_comment",
    )
    assert engine.rule_mode == "ai_guidance"
    assert engine.attachments == []
    assert engine.reply_text == ""
    assert engine.ai_guidance_rules[0]["attachments"][0]["id"] == "cmed_guide"
