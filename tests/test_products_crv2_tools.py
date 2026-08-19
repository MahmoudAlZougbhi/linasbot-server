"""CRV2 product tool wiring and import preview."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool  # noqa: E402
from services.products.media import store_product_media  # noqa: E402
from services.products.schemas import ProductWriteBody  # noqa: E402
from services.products.service import ProductsService  # noqa: E402


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'products_tools.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    import main  # noqa: F401
    import modules.mobile_products_api  # noqa: F401
    import modules.products_media_api  # noqa: F401

    yield tmp_path
    reset_engine_for_tests()


def _auth_headers(tenant_id: str) -> dict[str, str]:
    from services.dashboard_session_service import session_service

    session = session_service.create_session(
        user_id="u-products-tools",
        email="tools@example.com",
        role="admin",
        permissions=None,
        tenant_id=tenant_id,
    )
    token = session_service.cookie_value_for(session)
    return {"Authorization": f"Bearer {token}"}


def test_main_registers_product_routes(products_env: Path) -> None:
    from modules.core import app

    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/api/mobile/products" in paths
    assert "/api/mobile/products/import/preview" in paths
    assert "/api/mobile/products/media" in paths


def test_import_preview_endpoint(products_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers = _auth_headers("tenant-preview")
    csv_text = "name,price\nGood Serum,99\n,skip\n"
    res = client.post(
        "/api/mobile/products/import/preview",
        headers=headers,
        json={"csv_text": csv_text},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["valid_count"] == 1
    assert body["error_count"] == 1


def test_crv2_search_product_by_title_tool(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-crv2",
            body=ProductWriteBody(
                description="test product",
                name="Rose Gold Lipstick",
                price="45 AED",
                sizes=[],
                colors=["Rose"],
                links=[],
            ),
        )

    ctx = ToolContext(tenant_id="tenant-crv2", published_revision="rev-test", channel="instagram")
    out = dispatch_retrieval_tool(
        "search_product_by_title",
        {"title": "rose lipstick", "limit": 3},
        ctx,
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["match_count"] >= 1
    assert data["resolver"] == "deterministic"


def test_crv2_find_product_by_url_zero_credit(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-url",
            body=ProductWriteBody(
                description="test product",
                name="Shop Item",
                sizes=[],
                colors=[],
                links=[{"url": "https://shop.example.com/item-1", "label": "Buy", "sort_order": 0}],
            ),
        )

    ctx = ToolContext(tenant_id="tenant-url", published_revision="rev-test", channel="web_chat")
    out = dispatch_retrieval_tool(
        "find_product_by_url",
        {"url": "https://www.shop.example.com/item-1"},
        ctx,
    )
    assert out["ok"] is True
    assert out["data"]["match"]["name"] == "Shop Item"


def test_crv2_find_product_by_image_checksum_stub(products_env: Path) -> None:
    content = b"\xff\xd8\xff\xd9"
    stored = store_product_media(
        tenant_id="tenant-img",
        user_id="u1",
        filename="dup.jpg",
        content=content,
        content_type="image/jpeg",
    )
    media_id = str(stored["media_id"])

    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-img",
            body=ProductWriteBody(
                description="test product",
                name="Indexed Product",
                sizes=[],
                colors=[],
                images=[{"media_id": media_id, "sort_order": 0}],
                links=[],
            ),
        )

    ctx = ToolContext(tenant_id="tenant-img", published_revision="rev-test", channel="web_chat")
    out = dispatch_retrieval_tool(
        "find_product_by_image",
        {"image_media_id": media_id, "top_k": 10},
        ctx,
    )
    assert out["ok"] is True
    assert out["data"]["candidate_count"] >= 1
    assert out["data"]["matches"][0]["name"] == "Indexed Product"


def test_search_keeps_original_and_alternate_queries(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-q",
            body=ProductWriteBody(
                description="Face moisturizing cream.",
                name="Nivea Face Cream",
                sizes=[],
                colors=[],
                links=[],
            ),
        )

    ctx = ToolContext(tenant_id="tenant-q", published_revision="rev-test", channel="instagram_dm")
    out = dispatch_retrieval_tool(
        "search_product_by_title",
        {
            "title": "nevia creem lal wej",
            "original_query": "nevia creem lal wej",
            "alternate_queries": ["Nivea face cream"],
            "limit": 3,
        },
        ctx,
    )
    assert out["ok"] is True
    data = out["data"]
    assert data["original_query"] == "nevia creem lal wej"
    assert "Nivea face cream" in data["alternate_queries"]
    assert data["queries_used"][0] == "nevia creem lal wej"
    assert data["match_count"] >= 1
    assert data["matches"][0]["name"] == "Nivea Face Cream"
