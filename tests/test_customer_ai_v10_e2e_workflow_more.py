"""Customer AI V10 E2E scenarios 13-24. INTEGRATION SIMULATION, not live Meta."""

from __future__ import annotations

import pytest

from tests.customer_ai_v10_e2e_support import (
    create_product,
    publish_clinic,
    scripted_read,
    trace_from_outcome,
)
from tests.meta_compliance_helpers import _FakeFirestore

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures", "tests.customer_ai_v10_e2e_support")

SOURCE = "موعد Full Body\nجيب الاسم والعمر والطول والوزن والمنطقة واليوم المطلوب."


def _publish_graph(tenant: str, source_id: str = "req_full_body", dest: str = "APPOINTMENT"):
    from db.session import whatsapp_session
    from services.request_graphs.service import publish_graph

    with whatsapp_session(require=True) as db:
        return publish_graph(
            db,
            tenant_id=tenant,
            source_item_id=source_id,
            title="موعد Full Body" if dest == "APPOINTMENT" else "Order",
            source_text=SOURCE if dest == "APPOINTMENT" else "طلب كريم\nجيب الاسم والكمية",
            destination=dest,
            confirm=True,
        )


@pytest.mark.asyncio
async def test_s13_request_draft_fields(v2_env, products_db) -> None:
    await publish_clinic("t_e2e_s13")
    graph = _publish_graph("t_e2e_s13")
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e_s13",
        message="بدي احجز Full Body الخميس",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="cust13",
        conversation_id="c13",
        scripted_retrieval=scripted_read(["services:svc_full_body", "requests_appointments:req_full_body"]),
        fixture_answer={
            "reply_text": "تمام، منبلش نجمع معلومات الموعد.",
            "grounding_status": "grounded",
            "draft_actions": [{"action": "create_draft", "definition_id": graph["definition_id"]}],
        },
    )
    draft = (out.metadata or {}).get("draft_result") or {}
    assert draft.get("ok") is True
    draft_id = (draft.get("results") or [{}])[0].get("draft_id")
    assert draft_id
    from db.session import whatsapp_session
    from services.request_drafts.engine import apply_draft_action

    with whatsapp_session(require=True) as db:
        updated = apply_draft_action(
            db,
            tenant_id="t_e2e_s13",
            customer_id="cust13",
            action={
                "action": "update_fields",
                "draft_id": draft_id,
                "field_updates": {"name": "محمود", "age": 29, "height": 181, "national_id": "nope"},
            },
        )
    assert updated["ok"] is True
    assert updated["values"].get("name") == "محمود"
    assert "national_id" not in (updated.get("values") or {})
    rejected = updated.get("rejected_fields") or updated.get("rejected") or []
    assert rejected or "national_id" not in str(updated.get("values"))


@pytest.mark.asyncio
async def test_s14_two_drafts_multi_intent(v2_env, products_db) -> None:
    await publish_clinic("t_e2e_s14")
    appt = _publish_graph("t_e2e_s14")
    order = _publish_graph("t_e2e_s14", source_id="req_order", dest="ORDER")
    from db.session import whatsapp_session
    from services.request_drafts.engine import apply_draft_action

    with whatsapp_session(require=True) as db:
        a = apply_draft_action(
            db,
            tenant_id="t_e2e_s14",
            customer_id="cust14",
            action={"action": "create_draft", "definition_id": appt["definition_id"]},
        )
        b = apply_draft_action(
            db,
            tenant_id="t_e2e_s14",
            customer_id="cust14",
            action={"action": "create_draft", "definition_id": order["definition_id"]},
        )
        assert a["draft_id"] != b["draft_id"]
    from services.customer_reply_v2.open_drafts import list_open_collecting_drafts

    open_rows = list_open_collecting_drafts(tenant_id="t_e2e_s14", customer_id="cust14")
    assert len(open_rows) == 2


@pytest.mark.asyncio
async def test_s15_add_item_same_appointment(v2_env, products_db) -> None:
    await publish_clinic("t_e2e_s15")
    graph = _publish_graph("t_e2e_s15")
    from db.session import whatsapp_session
    from services.request_drafts.engine import apply_draft_action

    with whatsapp_session(require=True) as db:
        created = apply_draft_action(
            db,
            tenant_id="t_e2e_s15",
            customer_id="cust15",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        apply_draft_action(
            db,
            tenant_id="t_e2e_s15",
            customer_id="cust15",
            action={
                "action": "add_item",
                "draft_id": created["draft_id"],
                "item": {"type": "service", "id": "underarms"},
            },
        )
        added = apply_draft_action(
            db,
            tenant_id="t_e2e_s15",
            customer_id="cust15",
            action={
                "action": "add_item",
                "draft_id": created["draft_id"],
                "item": {"type": "service", "id": "bikini"},
            },
        )
        assert [item["id"] for item in added["items"]] == ["underarms", "bikini"]


@pytest.mark.asyncio
async def test_s16_replace_item_no_regex(v2_env, products_db) -> None:
    await publish_clinic("t_e2e_s16")
    graph = _publish_graph("t_e2e_s16")
    from db.session import whatsapp_session
    from services.request_drafts.engine import apply_draft_action

    with whatsapp_session(require=True) as db:
        created = apply_draft_action(
            db,
            tenant_id="t_e2e_s16",
            customer_id="cust16",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        apply_draft_action(
            db,
            tenant_id="t_e2e_s16",
            customer_id="cust16",
            action={
                "action": "add_item",
                "draft_id": created["draft_id"],
                "item": {"type": "service", "id": "underarms"},
            },
        )
        replaced = apply_draft_action(
            db,
            tenant_id="t_e2e_s16",
            customer_id="cust16",
            action={
                "action": "replace_item",
                "draft_id": created["draft_id"],
                "from_item": {"type": "service", "id": "underarms"},
                "to_item": {"type": "service", "id": "bikini"},
            },
        )
        assert [item["id"] for item in replaced["items"]] == ["bikini"]


@pytest.mark.asyncio
async def test_s17_pause_resume_after_history_window(v2_env, products_db) -> None:
    await publish_clinic("t_e2e_s17")
    graph = _publish_graph("t_e2e_s17")
    from db.session import whatsapp_session
    from services.request_drafts.engine import apply_draft_action

    with whatsapp_session(require=True) as db:
        created = apply_draft_action(
            db,
            tenant_id="t_e2e_s17",
            customer_id="cust17",
            action={"action": "create_draft", "definition_id": graph["definition_id"]},
        )
        apply_draft_action(
            db,
            tenant_id="t_e2e_s17",
            customer_id="cust17",
            action={
                "action": "update_fields",
                "draft_id": created["draft_id"],
                "field_updates": {"name": "محمود"},
            },
        )
        apply_draft_action(
            db,
            tenant_id="t_e2e_s17",
            customer_id="cust17",
            action={"action": "pause", "draft_id": created["draft_id"]},
        )
        resumed = apply_draft_action(
            db,
            tenant_id="t_e2e_s17",
            customer_id="cust17",
            action={"action": "resume", "draft_id": created["draft_id"]},
        )
        assert resumed["status"] == "collecting"
        assert resumed["values"]["name"] == "محمود"


@pytest.mark.asyncio
async def test_s18_product_media_send_no_second_tera(v2_env, products_db) -> None:
    from services.products.media import store_product_media

    stored = store_product_media(
        tenant_id="t_e2e_s18",
        user_id="u1",
        filename="p.jpg",
        content=b"\xff\xd8\xff\xd9media",
        content_type="image/jpeg",
    )
    product = create_product(
        "t_e2e_s18",
        name="Photo Cream",
        price="10",
        sizes=[],
        colors=[],
        images=[{"media_id": stored["media_id"], "sort_order": 0}],
        links=[],
    )
    await publish_clinic("t_e2e_s18")
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
    from services.customer_reply_v2.product_media_outbound import send_pending_product_media

    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e_s18",
        message="ابعتلي صور الكريم",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="u18",
        scripted_retrieval=scripted_read([], effort="low"),
        fixture_answer={
            "reply_text": "هيدي الصور.",
            "grounding_status": "grounded",
            "media_actions": [
                {"product_id": product["id"], "media_type": "images", "max_items": 5, "order": "configured_order"}
            ],
        },
    )
    delivery = (out.metadata or {}).get("media_delivery") or {}
    assert delivery.get("ok") is True
    assert delivery.get("extra_tera_call") is False
    assert delivery.get("items")
    captured: list[tuple] = []

    async def _cap(to, text, image, audio):
        captured.append((to, text, image, audio))

    user_data = {"tenant_id": "t_e2e_s18", "_pending_product_media": delivery}
    sent = await send_pending_product_media(
        user_data=user_data,
        sender_id="psid18",
        adapter=None,
        inbound_event_id=None,
        channel="instagram_dm",
        binding_id="bind18",
        capture_send=_cap,
    )
    assert sent["delivery_result"] == "simulated"
    assert captured
    assert str(captured[0][2]).startswith("product-media:")
    video = __import__("services.customer_reply_v2.media_actions", fromlist=["resolve_media_actions"]).resolve_media_actions(
        tenant_id="t_e2e_s18",
        actions=[{"product_id": product["id"], "media_type": "videos", "max_items": 1, "order": "configured_order"}],
        channel_capabilities={"max_media_items": 10},
    )
    assert video["ok"] is False
    assert video["error"] == "product_video_not_supported"


@pytest.mark.asyncio
async def test_s19_image_candidates_name_wins(v2_env, products_db) -> None:
    from unittest.mock import patch

    from services.products.media import store_product_media

    stored = store_product_media(
        tenant_id="t_e2e_s19",
        user_id="u1",
        filename="q.jpg",
        content=b"\xff\xd8\xff\xd9named",
        content_type="image/jpeg",
    )
    created = create_product(
        "t_e2e_s19",
        name="Indexed Serum",
        sizes=[],
        colors=[],
        images=[{"media_id": stored["media_id"], "sort_order": 0}],
        links=[],
    )
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t_e2e_s19", published_revision="rev", channel="instagram_dm")
    with patch("services.products.crv2_tools.vision_rerank_candidates") as vision:
        out = dispatch_retrieval_tool(
            "find_product_by_image",
            {"image_media_id": stored["media_id"], "product_name": "Indexed Serum", "top_k": 8},
            ctx,
        )
        vision.assert_not_called()
    assert out["data"]["resolver"] == "name_first"
    assert out["data"]["matches"][0]["id"] == created["id"]


@pytest.mark.asyncio
async def test_s20_safety_block_no_generative(v2_env, monkeypatch: pytest.MonkeyPatch) -> None:
    await publish_clinic("t_e2e_s20")
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm
    from services.safety_gateway import SafetyDecision

    async def _block(**_k):
        return SafetyDecision(decision="block", reasons=["policy:csam"], provider="openai", incident_id="inc20")

    monkeypatch.setattr("services.safety_gateway.safety_gateway.check_text", _block)
    out = await run_customer_reply_v2_dm(
        tenant_id="t_e2e_s20",
        message="child sexual content",
        detected_language="en",
        response_language="en",
        channel="instagram_dm",
        provider_sender_id="u20",
        scripted_retrieval=scripted_read(["services:svc_full_body"]),
        fixture_answer={"reply_text": "should not", "grounding_status": "grounded"},
    )
    trace = trace_from_outcome(message="blocked", channel="instagram_dm", out=out)
    assert out.reason == "safety_block"
    assert trace["luna_called"] is False
    assert trace["tera_called"] is False
    assert trace["faq_direct"] is not True
    assert (trace["metering"] or {}).get("ai_invocation_count") == 0


@pytest.mark.asyncio
async def test_s21_duplicate_webhook_ha_purposes(monkeypatch: pytest.MonkeyPatch) -> None:
    import services.meta_outbound_attempts as attempts
    import utils.utils

    db = _FakeFirestore()
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setattr(utils.utils, "get_firestore_db", lambda: db)
    calls = {"primary": 0, "dm": 0, "media": 0}

    async def send_primary():
        calls["primary"] += 1
        return {"success": True, "provider": "meta", "message_id": "m-primary"}

    async def send_dm():
        calls["dm"] += 1
        return {"success": True, "provider": "meta", "message_id": "m-dm"}

    async def send_media():
        calls["media"] += 1
        return {"success": True, "provider": "meta", "message_id": "m-media"}

    event_id = "ibe_" + "b" * 40
    for _ in range(2):
        await attempts.execute_guarded_meta_send(
            event_id=event_id, surface="instagram_comment", binding_id="b21", send=send_primary
        )
        await attempts.execute_guarded_meta_send(
            event_id=event_id,
            surface="instagram_comment",
            binding_id="b21",
            purpose="comment_private_dm",
            send=send_dm,
        )
        await attempts.execute_guarded_meta_send(
            event_id=event_id, surface="instagram_dm", binding_id="b21", purpose="product_media", send=send_media
        )
    assert calls == {"primary": 1, "dm": 1, "media": 1}


@pytest.mark.asyncio
async def test_s22_out_of_stock_searchable(v2_env, products_db) -> None:
    oos = create_product("t_e2e_s22", name="OOS Cream", availability="out_of_stock", sizes=[], colors=[], links=[])
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t_e2e_s22", published_revision="rev", channel="instagram_dm")
    search = dispatch_retrieval_tool("search_product_by_title", {"title": "OOS Cream"}, ctx)
    assert search["data"]["match_count"] == 1
    details = dispatch_retrieval_tool("get_product_details", {"product_id": oos["id"]}, ctx)
    assert details["data"]["product"]["in_stock"] is False


@pytest.mark.asyncio
async def test_s23_deleted_inactive_not_resolved(v2_env, products_db) -> None:
    hidden = create_product(
        "t_e2e_s23", name="ZZHiddenUniqueInactive", availability="inactive", sizes=[], colors=[], links=[]
    )
    live = create_product("t_e2e_s23", name="LiveZebraOnly", sizes=[], colors=[], links=[])
    from db.session import whatsapp_session
    from services.customer_reply_v2.media_actions import resolve_media_actions
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool
    from services.products.service import ProductsService

    ctx = ToolContext(tenant_id="t_e2e_s23", published_revision="rev", channel="instagram_dm")
    hidden_search = dispatch_retrieval_tool("search_product_by_title", {"title": "ZZHiddenUniqueInactive"}, ctx)
    assert hidden_search["data"]["match_count"] == 0
    with whatsapp_session(require=True) as session:
        ProductsService(session).delete_product(tenant_id="t_e2e_s23", product_id=live["id"])
    gone = dispatch_retrieval_tool("search_product_by_title", {"title": "LiveZebraOnly"}, ctx)
    assert gone["data"]["match_count"] == 0
    media = resolve_media_actions(
        tenant_id="t_e2e_s23",
        actions=[{"product_id": hidden["id"], "media_type": "images", "max_items": 1, "order": "configured_order"}],
        channel_capabilities={"max_media_items": 10},
    )
    assert media["ok"] is False


@pytest.mark.asyncio
async def test_s24_comment_appointment_privacy(v2_env, products_db) -> None:
    await publish_clinic("t_e2e_s24")
    graph = _publish_graph("t_e2e_s24")
    from services.customer_reply_v2.comment_runtime import run_customer_reply_v2_comment

    out = await run_customer_reply_v2_comment(
        tenant_id="t_e2e_s24",
        comment_text="بدي احجز Full Body الخميس",
        detected_language="ar",
        response_language="ar",
        channel="instagram_comment",
        scripted_retrieval=scripted_read(
            ["comments:rule_ai_public", "services:svc_full_body", "requests_appointments:req_full_body"]
        ),
        fixture_answer={
            "reply_text": "للتفاصيل الخاصة كمّلي بالـ DM.",
            "grounding_status": "grounded",
            "draft_actions": [{"action": "create_draft", "definition_id": graph["definition_id"]}],
        },
    )
    draft = (out.metadata or {}).get("draft_result") or {}
    assert draft.get("error") == "public_comment_refused"
    assert "DM" in (out.reply or "") or "الخاص" in (out.reply or "") or "خاص" in (out.reply or "")
    assert out.reason != "requests_comment_dm_invite"
    trace = trace_from_outcome(message="بدي احجز Full Body الخميس", channel="instagram_comment", out=out)
    assert trace["luna_called"] is True
    assert "services:svc_full_body" in trace["selected_source_ids"]
    assert "requests_appointments:req_full_body" in trace["selected_source_ids"]
