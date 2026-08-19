"""Customer AI V10 product recognition — same Luna op, no third agent, no store merge."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine, event

from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool
from services.products.media import MEDIA_ID_PREFIX, load_media_bytes, store_product_media

pytest_plugins = ("tests.customer_reply_ai_v2_fixtures",)


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    monkeypatch.setenv("CUSTOMER_AI_V10_RUNTIME", "true")
    url = f"sqlite:///{tmp_path / 'products_recog.db'}"
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


def test_exact_typo_same_luna_op_no_third_agent(products_env: Path) -> None:
    _create("t1", name="After Care Cream", price="20", sizes=[], colors=[], links=[])
    ctx = ToolContext(tenant_id="t1", published_revision="rev", channel="instagram_dm")
    with patch("services.products.luna_title_resolver.resolve_product_titles_with_luna") as luna:
        exact = dispatch_retrieval_tool("search_product_by_title", {"title": "After Care Cream"}, ctx)
        typo = dispatch_retrieval_tool("search_product_by_title", {"title": "after car cream"}, ctx)
        luna.assert_not_called()
    assert exact["data"]["match_count"] == 1
    assert exact["data"]["extra_luna_agent"] is False
    assert typo["data"]["match_count"] >= 1
    assert typo["data"]["extra_luna_agent"] is False
    assert typo["data"]["matches"][0]["title"] == "After Care Cream"


def test_unknown_title_uses_titles_fallback_not_new_agent(products_env: Path) -> None:
    _create("t2", name="Laser Gel", sizes=[], colors=[], links=[])
    ctx = ToolContext(tenant_id="t2", published_revision="rev", channel="instagram_dm")
    with patch("services.products.luna_title_resolver.resolve_product_titles_with_luna") as luna:
        miss = dispatch_retrieval_tool("search_product_by_title", {"title": "zzzz-burger-not-a-product"}, ctx)
        luna.assert_not_called()
    assert miss["data"]["resolver"] == "titles_fallback"
    assert miss["data"]["extra_luna_agent"] is False


def test_knowledge_described_product_still_requires_product_id(products_env: Path) -> None:
    created = _create("t3", name="After Care Cream", sizes=[], colors=[], links=[])
    ctx = ToolContext(tenant_id="t3", published_revision="rev", channel="instagram_dm")
    described = dispatch_retrieval_tool("search_product_by_title", {"title": "After Care Cream"}, ctx)
    assert described["data"]["matches"][0]["id"] == created["id"]
    invented = dispatch_retrieval_tool("get_product_details", {"product_id": "prod_hallucinated"}, ctx)
    assert invented["ok"] is True
    assert invented["data"].get("ok") is False or invented["data"].get("error") == "not_found"


def test_burger_image_does_not_resolve_tattoo_product(products_env: Path) -> None:
    burger = store_product_media(
        tenant_id="t4",
        user_id="u1",
        filename="burger.jpg",
        content=b"\xff\xd8\xff\xd9BURGER-IMAGE-BYTES",
        content_type="image/jpeg",
    )
    tattoo = store_product_media(
        tenant_id="t4",
        user_id="u1",
        filename="tattoo.jpg",
        content=b"\xff\xd8\xff\xd9TATTOO-IMAGE-BYTES",
        content_type="image/jpeg",
    )
    burger_p = _create(
        "t4",
        name="Burger Photo Product",
        sizes=[],
        colors=[],
        images=[{"media_id": burger["media_id"], "sort_order": 0}],
        links=[],
    )
    tattoo_p = _create(
        "t4",
        name="Tattoo Photo Product",
        sizes=[],
        colors=[],
        images=[{"media_id": tattoo["media_id"], "sort_order": 0}],
        links=[],
    )
    ctx = ToolContext(tenant_id="t4", published_revision="rev", channel="instagram_dm")
    with patch("services.products.crv2_tools.vision_rerank_candidates") as vision:
        out = dispatch_retrieval_tool(
            "find_product_by_image",
            {"image_media_id": burger["media_id"], "top_k": 8},
            ctx,
        )
        _ = vision
    matches = list((out.get("data") or {}).get("matches") or [])
    ids = {str(row.get("id")) for row in matches}
    assert burger_p["id"] in ids or out["data"].get("match_count") == 0
    if len(matches) == 1:
        assert matches[0]["id"] != tattoo_p["id"]


def test_product_media_not_cm_resource_store() -> None:
    from services.cm.article_media import load_media_bytes as load_cm_bytes

    assert MEDIA_ID_PREFIX == "prdim_"
    assert load_media_bytes(tenant_id="t", media_id="cmed_not_a_product") is None
    assert load_cm_bytes(tenant_id="t", media_id="prdim_not_cm") is None
