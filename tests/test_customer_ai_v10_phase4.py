"""Customer AI V10 Phase 4 — product search, titles fallback, media_actions."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event

from tests.cm_test_helpers import publish_test_content
from tests.customer_reply_ai_v2_helpers import _rich_sections

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("CUSTOMER_AI_V10_RUNTIME", "true")
    url = f"sqlite:///{tmp_path / 'products_v10.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    from db.models import Base
    from db.session import reset_engine_for_tests

    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()


def _create(tenant: str, **kwargs):
    from db.session import whatsapp_session
    from services.products.schemas import ProductWriteBody
    from services.products.service import ProductsService

    with whatsapp_session(require=True) as session:
        kwargs.setdefault("description", kwargs.get("name") or "test product")
        return ProductsService(session).create_product(tenant_id=tenant, body=ProductWriteBody(**kwargs))


def test_exact_and_typo_and_arabizi_search(products_env: Path) -> None:
    _create("t1", name="Rose Gold Lipstick", price="45 AED", sizes=[], colors=["Rose"], links=[])
    _create("t1", name="Full Body Cream", price="20", sizes=[], colors=[], links=[])
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t1", published_revision="rev", channel="instagram_dm")
    exact = dispatch_retrieval_tool("search_product_by_title", {"title": "Rose Gold Lipstick"}, ctx)
    assert exact["data"]["match_count"] == 1
    assert exact["data"]["extra_luna_agent"] is False
    assert "price" not in exact["data"]["matches"][0]
    assert "images" not in exact["data"]["matches"][0]

    typo = dispatch_retrieval_tool("search_product_by_title", {"title": "rose gold lipstik"}, ctx)
    assert typo["data"]["match_count"] >= 1
    assert typo["data"]["matches"][0]["title"] == "Rose Gold Lipstick"

    arabizi = dispatch_retrieval_tool("search_product_by_title", {"title": "ful body cream"}, ctx)
    assert arabizi["data"]["match_count"] >= 1
    assert "Cream" in arabizi["data"]["matches"][0]["title"]


def test_titles_fallback_same_loop_no_extra_agent(products_env: Path) -> None:
    _create("t2", name="Serum One", price="10", sizes=[], colors=[], links=[])
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t2", published_revision="rev", channel="instagram_dm")
    with patch("services.products.luna_title_resolver.resolve_product_titles_with_luna") as luna:
        miss = dispatch_retrieval_tool("search_product_by_title", {"title": "zzzz-unknown-item"}, ctx)
        luna.assert_not_called()
    assert miss["data"]["resolver"] == "titles_fallback"
    assert miss["data"]["extra_luna_agent"] is False
    titles = miss["data"]["titles_fallback"]["titles"]
    assert titles
    assert {"id", "title", "status"} <= set(titles[0].keys())
    assert "price" not in titles[0]
    assert "images" not in titles[0]
    page = dispatch_retrieval_tool("list_product_titles", {"offset": 0, "limit": 80}, ctx)
    assert page["ok"] is True
    assert page["data"]["full_catalog"] is False
    assert "price" not in str(page["data"]["titles"])


def test_status_rules_and_tenant_isolation(products_env: Path) -> None:
    oos = _create("ta", name="OOS Cream", availability="out_of_stock", sizes=[], colors=[], links=[])
    hidden_row = _create("ta", name="ZZHiddenUniqueInactive", availability="inactive", sizes=[], colors=[], links=[])
    live = _create("ta", name="LiveZebraOnly", sizes=[], colors=[], links=[])
    other = _create("tb", name="Other Tenant Cream", sizes=[], colors=[], links=[])
    from db.session import whatsapp_session
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool
    from services.products.service import ProductsService

    ctx_a = ToolContext(tenant_id="ta", published_revision="rev", channel="instagram_dm")
    ctx_b = ToolContext(tenant_id="tb", published_revision="rev", channel="instagram_dm")

    oos_search = dispatch_retrieval_tool("search_product_by_title", {"title": "OOS Cream"}, ctx_a)
    assert oos_search["data"]["match_count"] == 1
    details = dispatch_retrieval_tool("get_product_details", {"product_id": oos["id"]}, ctx_a)
    assert details["data"]["product"]["in_stock"] is False
    assert details["data"]["product"]["image_count"] == 0
    assert "images" not in details["data"]["product"]

    hidden = dispatch_retrieval_tool("search_product_by_title", {"title": "ZZHiddenUniqueInactive"}, ctx_a)
    assert hidden["data"]["match_count"] == 0
    inactive_details = dispatch_retrieval_tool("get_product_details", {"product_id": hidden_row["id"]}, ctx_a)
    assert inactive_details["data"].get("error") == "not_customer_facing"
    hidden_details = dispatch_retrieval_tool("get_product_details", {"product_id": oos["id"]}, ctx_b)
    assert hidden_details["ok"] is True
    assert hidden_details["data"].get("ok") is False

    other_hit = dispatch_retrieval_tool("search_product_by_title", {"title": "Other Tenant Cream"}, ctx_a)
    assert other_hit["data"]["match_count"] == 0
    own = dispatch_retrieval_tool("search_product_by_title", {"title": "Other Tenant Cream"}, ctx_b)
    assert own["data"]["matches"][0]["id"] == other["id"]

    with whatsapp_session(require=True) as session:
        ProductsService(session).delete_product(tenant_id="ta", product_id=live["id"])
    gone = dispatch_retrieval_tool("search_product_by_title", {"title": "LiveZebraOnly"}, ctx_a)
    assert gone["data"]["match_count"] == 0
    gone_details = dispatch_retrieval_tool("get_product_details", {"product_id": live["id"]}, ctx_a)
    assert gone_details["data"].get("error") == "not_found"


def test_product_search_does_not_return_services(products_env: Path) -> None:
    _create("t3", name="Full body laser", sizes=[], colors=[], links=[])
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t3", published_revision="rev", channel="instagram_dm")
    out = dispatch_retrieval_tool("search_product_by_title", {"title": "Full body laser"}, ctx)
    assert out["data"]["match_count"] == 1
    assert out["data"]["matches"][0]["id"]
    assert not str(out["data"]["matches"][0]["id"]).startswith("svc_")


def test_clear_name_skips_vision(products_env: Path) -> None:
    from services.products.media import store_product_media

    stored = store_product_media(
        tenant_id="t4",
        user_id="u1",
        filename="p.jpg",
        content=b"\xff\xd8\xff\xd9named",
        content_type="image/jpeg",
    )
    created = _create(
        "t4",
        name="Indexed Serum",
        sizes=[],
        colors=[],
        images=[{"media_id": stored["media_id"], "sort_order": 0}],
        links=[],
    )
    from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool

    ctx = ToolContext(tenant_id="t4", published_revision="rev", channel="web_chat")
    with patch("services.products.crv2_tools.vision_rerank_candidates") as vision:
        out = dispatch_retrieval_tool(
            "find_product_by_image",
            {"image_media_id": stored["media_id"], "product_name": "Indexed Serum", "top_k": 8},
            ctx,
        )
        vision.assert_not_called()
    assert out["data"]["resolver"] == "name_first"
    assert out["data"]["vision_used"] is False
    assert out["data"]["matches"][0]["id"] == created["id"]


def test_image_candidates_clamped_3_to_8(products_env: Path) -> None:
    from services.products.crv2_tools import _clamp_image_top_k

    assert _clamp_image_top_k(1) == 3
    assert _clamp_image_top_k(10) == 8
    assert _clamp_image_top_k(5) == 5


def test_media_actions_resolve_and_isolation(products_env: Path) -> None:
    from services.products.media import store_product_media

    stored = store_product_media(
        tenant_id="t5",
        user_id="u1",
        filename="p.jpg",
        content=b"\xff\xd8\xff\xd9media",
        content_type="image/jpeg",
    )
    product = _create(
        "t5",
        name="Photo Cream",
        sizes=[],
        colors=[],
        images=[{"media_id": stored["media_id"], "sort_order": 0}],
        links=[],
    )
    from services.customer_reply_v2.media_actions import parse_media_actions, resolve_media_actions

    actions = parse_media_actions(
        [{"product_id": product["id"], "media_type": "images", "max_items": 5, "order": "configured_order"}]
    )
    dm = resolve_media_actions(
        tenant_id="t5",
        actions=actions,
        channel_capabilities={"max_media_items": 10},
        idempotency_key="turn-1",
    )
    assert dm["ok"] is True
    assert dm["ai_charged"] is False
    assert dm["extra_tera_call"] is False
    assert dm["items"][0]["media_id"] == stored["media_id"]
    again = resolve_media_actions(
        tenant_id="t5",
        actions=actions,
        channel_capabilities={"max_media_items": 10},
        idempotency_key="turn-1",
    )
    assert again["delivery_fingerprint"] == dm["delivery_fingerprint"]

    comment = resolve_media_actions(
        tenant_id="t5",
        actions=actions,
        channel_capabilities={"max_media_items": 0},
    )
    assert comment["ok"] is False
    assert comment["error"] == "channel_cannot_send_media"

    foreign = resolve_media_actions(
        tenant_id="other",
        actions=actions,
        channel_capabilities={"max_media_items": 10},
    )
    assert foreign["ok"] is False
    assert foreign["error"] == "product_not_found"


@pytest.mark.asyncio
async def test_tera_media_actions_no_ai_charge(v2_env, products_env: Path) -> None:
    from services.products.media import store_product_media

    stored = store_product_media(
        tenant_id="t_media",
        user_id="u1",
        filename="p.jpg",
        content=b"\xff\xd8\xff\xd9flow",
        content_type="image/jpeg",
    )
    product = _create(
        "t_media",
        name="Flow Cream",
        sizes=[],
        colors=[],
        images=[{"media_id": stored["media_id"], "sort_order": 0}],
        links=[],
    )
    await publish_test_content("t_media", _rich_sections())
    from services.customer_reply_v2.orchestrator import run_customer_reply_v2_dm

    out = await run_customer_reply_v2_dm(
        tenant_id="t_media",
        message="ابعتلي صور الكريم",
        detected_language="ar",
        response_language="ar",
        channel="instagram_dm",
        provider_sender_id="u_media",
        scripted_retrieval=[{"final_plan": {"evidence_status": "insufficient_final", "selected_source_ids": []}}],
        fixture_answer={
            "reply_text": "أكيد، هيدي صور المنتج.",
            "grounding_status": "grounded",
            "media_actions": [
                {
                    "product_id": product["id"],
                    "media_type": "images",
                    "max_items": 5,
                    "order": "configured_order",
                }
            ],
        },
    )
    delivery = out.metadata.get("media_delivery") or {}
    assert delivery.get("ok") is True
    assert delivery.get("ai_charged") is False
    assert delivery.get("extra_tera_call") is False
    assert delivery.get("items")
    metering = out.metadata.get("metering") or {}
    media_ops = [row for row in metering.get("invocations") or [] if row["operation"] == "media_delivery"]
    assert media_ops
    assert media_ops[0]["is_ai"] is False
    assert metering.get("ai_invocation_count") == len(
        [row for row in metering.get("invocations") or [] if row.get("is_ai")]
    )
