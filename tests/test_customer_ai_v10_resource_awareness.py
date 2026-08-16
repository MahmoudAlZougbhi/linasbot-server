"""Luna sees resource counts only; Tera gets selected-file descriptors and resource_actions."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from tests.cm_test_helpers import publish_test_content

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)

_WOMEN = {
    "id": "kn_women",
    "title": "Laser Hair Removal Women",
    "body": "Women-specific laser content.",
    "status": "active",
    "attachments": [
        {
            "id": "res_women_before",
            "kind": "image",
            "title": "Women Before Laser Hair Removal",
            "description": "Send when the customer asks for women before photos.",
            "filename": "women-before.png",
            "url": "https://private.example/women-before.png",
            "status": "active",
        }
    ],
}
_SERVICE = {
    "id": "kn_service",
    "title": "Laser Hair Removal Service",
    "body": "Generic service file.",
    "status": "active",
    "attachments": [
        {
            "id": "res_service_before",
            "kind": "image",
            "title": "Service Before",
            "description": "Generic before photo.",
            "filename": "service-before.png",
            "url": "https://private.example/service-before.png",
            "status": "active",
        }
    ],
}


async def _publish_laser(tenant_id: str) -> None:
    await publish_test_content(tenant_id, {"knowledge": {"items": [_WOMEN, _SERVICE]}})


@pytest.mark.asyncio
async def test_luna_titles_have_counts_not_urls(v2_env):
    await _publish_laser("t_luna_res")
    from services.cm.version_store import load_published_content
    from services.customer_reply_v2.operational_titles import collect_operational_titles

    titles = collect_operational_titles(load_published_content("t_luna_res")[1])
    by_id = {row["id"]: row for row in titles}
    women = by_id["knowledge:kn_women"]
    service = by_id["knowledge:kn_service"]
    assert women["resource_summary"] == {
        "images": 1,
        "videos": 0,
        "files": 0,
        "links": 0,
        "has_resources": True,
    }
    assert service["resource_summary"]["images"] == 1
    blob = str(titles)
    assert "https://private.example" not in blob
    assert "women-before.png" not in blob
    assert "resource_ref" not in blob
    assert "storage" not in blob.lower()


@pytest.mark.asyncio
async def test_luna_read_strips_resources_tera_gets_selected_file_only(v2_env):
    await _publish_laser("t_luna_read")
    from services.customer_reply_v2.answer_luna import build_answer_messages
    from services.customer_reply_v2.manifest import get_cached_manifest
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    rev, _ = get_cached_manifest("t_luna_read")
    ctx = ToolContext(tenant_id="t_luna_read", published_revision=rev, channel="instagram_dm")
    listed = dispatch_retrieval_tool("list_published_cm_items", {"section_ids": ["knowledge"]}, ctx)
    listed_ids = {row["item_id"]: row["resource_summary"] for row in listed["data"]["items"]}
    assert listed_ids["knowledge:kn_women"]["images"] == 1
    assert "https://" not in str(listed)

    out = dispatch_retrieval_tool("read_published_cm_items", {"item_ids": ["knowledge:kn_women"]}, ctx)
    assert out["ok"] is True
    luna_row = out["data"]["evidence"][0]
    assert luna_row["source_id"] == "knowledge:kn_women"
    assert luna_row["resource_summary"]["images"] == 1
    assert "allowed_resources" not in luna_row
    luna_blob = str(luna_row)
    assert "https://private.example" not in luna_blob
    assert "CASE EXAMPLES" not in luna_blob
    assert "Women-specific laser content" in luna_row["content"]

    rec = ctx.evidence_acc[0]
    refs = {row["resource_ref"] for row in rec.allowed_resources}
    assert refs == {"res_women_before"}
    assert "res_service_before" not in refs
    tera_blob = str(rec.allowed_resources)
    assert "https://private.example" not in tera_blob
    assert "storage" not in tera_blob.lower()

    msgs = build_answer_messages(
        message="ابعتلي صور laser hair removal للنساء",
        fixed_context={
            "published_revision": rev,
            "ai_basics": {"advanced_instructions": "x"},
            "style": {"style_body": "y"},
            "ai_profile": {},
        },
        evidence=list(ctx.evidence_acc),
        evidence_status="sufficient",
        customer_profile={},
        history_messages=[],
        comment_context=None,
        channel="instagram_dm",
        published_revision=rev,
        response_language="ar",
        detected_language="ar",
    )
    blob = str(msgs)
    assert "allowed_resources" in blob
    assert "res_women_before" in blob
    assert "res_service_before" not in blob
    assert "resource_actions" in blob
    assert "send_resource" in blob


@pytest.mark.asyncio
async def test_invented_and_cross_file_resource_actions_rejected(v2_env):
    await _publish_laser("t_res_act")
    from services.customer_reply_v2.resource_actions import parse_resource_actions, resolve_resource_actions

    parsed = parse_resource_actions(
        [
            {"action": "send_resource", "resource_ref": "res_women_before"},
            {"action": "send_file", "resource_ref": "res_women_before"},
            {"resource_ref": "ignored"},
        ]
    )
    assert parsed == [{"action": "send_resource", "resource_ref": "res_women_before"}]

    invented = resolve_resource_actions(
        tenant_id="t_res_act",
        actions=[{"action": "send_resource", "resource_ref": "res_invented"}],
        allowed_source_ids=["knowledge:kn_women"],
        channel_capabilities={"max_media_items": 5},
    )
    assert invented["ok"] is False
    assert invented["claimed_sent"] is False

    cross = resolve_resource_actions(
        tenant_id="t_res_act",
        actions=[{"action": "send_resource", "resource_ref": "res_service_before"}],
        allowed_source_ids=["knowledge:kn_women"],
        channel_capabilities={"max_media_items": 5},
    )
    assert cross["ok"] is False
    assert cross["error"] == "resource_not_on_selected_file"
    assert cross["claimed_sent"] is False

    ok = resolve_resource_actions(
        tenant_id="t_res_act",
        actions=[{"action": "send_resource", "resource_ref": "res_women_before"}],
        allowed_source_ids=["knowledge:kn_women"],
        channel_capabilities={"max_media_items": 5},
        idempotency_key="turn1",
    )
    assert ok["ok"] is True
    assert ok["claimed_sent"] is False
    assert ok["delivery_result"] == "resolved_pending_channel_send"
    assert ok["items"][0]["resource_ref"] == "res_women_before"


@pytest.mark.asyncio
async def test_plan_resources_does_not_claim_send(v2_env):
    await _publish_laser("t_res_plan")
    from services.customer_reply_v2.resource_actions import plan_resources_for_turn

    answer = SimpleNamespace(
        resource_actions=[{"action": "send_resource", "resource_ref": "res_women_before"}],
        raw_structured={},
    )
    out = plan_resources_for_turn(
        tenant_id="t_res_plan",
        answer=answer,
        channel_metadata={"channel_capabilities": {"max_media_items": 5}},
        allowed_source_ids=["knowledge:kn_women"],
        idempotency_key="k1",
    )
    assert out["resource_delivery"]["ok"] is True
    assert out["resource_delivery"]["claimed_sent"] is False
    public = plan_resources_for_turn(
        tenant_id="t_res_plan",
        answer=answer,
        channel_metadata={"channel_capabilities": {"max_media_items": 0}},
        allowed_source_ids=["knowledge:kn_women"],
        idempotency_key="k2",
    )
    assert public["resource_delivery"]["ok"] is False
    assert public["resource_delivery"]["error"] == "channel_cannot_send_media"
    assert public["resource_delivery"]["claimed_sent"] is False
