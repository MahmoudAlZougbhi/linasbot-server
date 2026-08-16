"""Outbound AI Setup resources, product video, signed Web Chat URLs, WhatsApp policy."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.cm_test_helpers import publish_test_content
from tests.customer_ai_v10_e2e_support import create_product

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures", "tests.customer_ai_v10_e2e_support")


@pytest.mark.asyncio
async def test_product_video_resolves_when_stored(v2_env, products_db):
    from services.customer_reply_v2.media_actions import resolve_media_actions
    from services.products.media import store_product_media

    stored = store_product_media(
        tenant_id="t_vid",
        user_id="u1",
        filename="clip.mp4",
        content=b"\x00\x00\x00\x18ftypmp42",
        content_type="video/mp4",
    )
    assert stored["ok"] is True
    product = create_product(
        "t_vid",
        name="After Care Cream",
        images=[{"media_id": stored["media_id"], "sort_order": 0}],
    )
    plan = resolve_media_actions(
        tenant_id="t_vid",
        actions=[{"product_id": product["id"], "media_type": "videos", "max_items": 1, "order": "configured_order"}],
        channel_capabilities={"max_media_items": 10},
    )
    assert plan["ok"] is True
    assert plan["items"][0]["media_type"] == "videos"
    assert plan["items"][0]["media_id"] == stored["media_id"]


@pytest.mark.asyncio
async def test_setup_resource_simulated_send_does_not_claim(v2_env):
    from services.cm.article_media import store_article_media
    from services.customer_reply_v2.setup_resource_outbound import send_pending_setup_resources

    stored = store_article_media(
        tenant_id="t_out",
        user_id="u1",
        filename="women-before.png",
        content=b"\x89PNG\r\n\x1a\n",
        content_type="image/png",
    )
    women = {
        "id": "kn_women",
        "title": "Laser Hair Removal Women",
        "body": "Women file.",
        "status": "active",
        "attachments": [
            {
                "id": stored["media_id"],
                "kind": "image",
                "title": "Women Before",
                "description": "Women before example.",
                "status": "active",
            }
        ],
    }
    await publish_test_content("t_out", {"knowledge": {"items": [women]}})
    captured: list[tuple] = []

    async def _cap(to, text, image, audio):
        captured.append((to, text, image, audio))

    user_data = {
        "tenant_id": "t_out",
        "_pending_setup_resources": {
            "ok": True,
            "items": [{"resource_ref": stored["media_id"], "resource_type": "image", "title": "Women Before"}],
        },
    }
    sent = await send_pending_setup_resources(
        user_data=user_data,
        sender_id="psid1",
        adapter=None,
        inbound_event_id=None,
        channel="instagram_dm",
        binding_id="b1",
        capture_send=_cap,
    )
    assert sent["delivery_result"] == "simulated"
    assert sent["claimed_sent"] is False
    assert captured and str(captured[0][2]).startswith("setup-resource:")


@pytest.mark.asyncio
async def test_whatsapp_resource_send_blocked_by_product_policy(v2_env, monkeypatch):
    monkeypatch.setenv("WHATSAPP_CLOUD_PUBLIC_AVAILABILITY", "false")
    monkeypatch.setenv("WHATSAPP_CLOUD_OUTBOUND_SENDS_ENABLED", "false")
    from services.customer_reply_v2.setup_resource_outbound import send_pending_setup_resources

    out = await send_pending_setup_resources(
        user_data={"tenant_id": "t_wa", "_pending_setup_resources": {"ok": True, "items": [{"resource_ref": "x"}]}},
        sender_id="1",
        adapter=SimpleNamespace(),
        inbound_event_id=None,
        channel="whatsapp_dm",
        binding_id="b",
    )
    assert out["error"] == "whatsapp_disabled_by_product_policy"
    assert out["delivery_result"] == "DISABLED BY PRODUCT POLICY"
    assert out["claimed_sent"] is False


def test_web_chat_signed_url_has_no_private_key(v2_env, monkeypatch):
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    from services.customer_reply_v2.resource_signed_urls import mint_resource_card, verify_resource_token

    card = mint_resource_card(
        tenant_id="t_web",
        resource_ref="cmed_abc",
        title="Map",
        description="Parking",
        resource_type="image",
    )
    blob = str(card)
    assert "PRIVATE KEY" not in blob
    assert "BEGIN " not in blob
    assert card["url"].startswith("/web-chat/resources/")
    token = card["url"].rsplit("/", 1)[-1]
    parsed = verify_resource_token(token)
    assert parsed["ok"] is True
    assert parsed["tenant_id"] == "t_web"
    assert parsed["resource_ref"] == "cmed_abc"


def test_comment_rule_resources_appear_on_decision(v2_env):
    from services.customer_reply_v2.comment_rule_engine import evaluate_comment_engine

    section = {
        "rules": [
            {
                "id": "rule_auto",
                "enabled": True,
                "rule_mode": "deterministic",
                "trigger_type": "contains_any",
                "keywords": ["price"],
                "action": "reply_comment_and_dm",
                "reply_template": "Check DM",
                "dm_template": "Here is the menu",
                "attachments": [
                    {
                        "id": "cmed_menu",
                        "kind": "image",
                        "title": "Menu",
                        "description": "Send the menu photo",
                        "status": "active",
                    }
                ],
            }
        ]
    }
    engine = evaluate_comment_engine(section, comment_text="price please", channel="instagram_comment")
    assert engine.matched is True
    assert engine.attachments[0]["id"] == "cmed_menu"
