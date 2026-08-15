"""AI Products Phase 2 — availability, image match, context, reply-to, xlsx."""

from __future__ import annotations

import base64
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.customer_reply_v2.retrieval_tools import ToolContext, dispatch_retrieval_tool  # noqa: E402
from services.products.active_context import get_active_product, set_active_product  # noqa: E402
from services.products.availability import normalize_availability  # noqa: E402
from services.products.image_fingerprint import compute_average_phash, sha256_hex  # noqa: E402
from services.products.image_index import find_image_candidates  # noqa: E402
from services.products.media import store_product_media  # noqa: E402
from services.products.reply_to_map import record_sent_product_message, resolve_reply_to_product  # noqa: E402
from services.products.schemas import ProductWriteBody  # noqa: E402
from services.products.search import search_product_by_title  # noqa: E402
from services.products.service import ProductsService  # noqa: E402
from services.products.xlsx_import import parse_xlsx_bytes  # noqa: E402


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'products_phase2.db'}"
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
        user_id="u-products-p2",
        email="p2@example.com",
        role="admin",
        permissions=None,
        tenant_id=tenant_id,
    )
    token = session_service.cookie_value_for(session)
    return {"Authorization": f"Bearer {token}"}


def test_availability_normalization() -> None:
    assert normalize_availability("In Stock") == "in_stock"
    assert normalize_availability("out of stock") == "out_of_stock"
    assert normalize_availability("inactive") == "inactive"


def test_inactive_excluded_from_customer_search(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-avail",
            body=ProductWriteBody(name="Hidden Serum", availability="inactive", sizes=[], colors=[], links=[]),
        )
        svc.create_product(
            tenant_id="tenant-avail",
            body=ProductWriteBody(name="Visible Cream", availability="in_stock", sizes=[], colors=[], links=[]),
        )
        matches = search_product_by_title(session, tenant_id="tenant-avail", title="cream", limit=5)
    assert all(m["name"] != "Hidden Serum" for m in matches)
    assert any(m["name"] == "Visible Cream" for m in matches)


def test_out_of_stock_in_search_and_details(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        created = svc.create_product(
            tenant_id="tenant-oos",
            body=ProductWriteBody(
                name="Limited Lipstick",
                availability="out_of_stock",
                price="40 AED",
                sizes=[],
                colors=[],
                links=[],
            ),
        )
        matches = search_product_by_title(session, tenant_id="tenant-oos", title="lipstick", limit=3)
        assert matches[0]["availability"] == "out_of_stock"
        details = svc.get_product(tenant_id="tenant-oos", product_id=created["id"])
        assert details["availability"] == "out_of_stock"


def test_image_index_checksum_match(products_env: Path) -> None:
    content = b"\xff\xd8\xff\xd9"
    stored = store_product_media(
        tenant_id="tenant-img2",
        user_id="u1",
        filename="p.jpg",
        content=content,
        content_type="image/jpeg",
    )
    media_id = str(stored["media_id"])
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-img2",
            body=ProductWriteBody(
                name="Indexed Bag",
                sizes=[],
                colors=[],
                images=[{"media_id": media_id, "sort_order": 0}],
                links=[],
            ),
        )
        candidates = find_image_candidates(session, tenant_id="tenant-img2", query_bytes=content, top_k=8)
    assert len(candidates) >= 1


def test_active_product_context(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        product = svc.create_product(
            tenant_id="tenant-ctx",
            body=ProductWriteBody(name="Context Shoe", sizes=[], colors=[], links=[]),
        )
        set_active_product(
            session,
            tenant_id="tenant-ctx",
            conversation_id="conv-1",
            product_id=product["id"],
            source="title_search",
        )
        active = get_active_product(session, tenant_id="tenant-ctx", conversation_id="conv-1")
        assert active is not None
        assert active["active_product_id"] == product["id"]


def test_reply_to_product_resolution(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        product = svc.create_product(
            tenant_id="tenant-reply",
            body=ProductWriteBody(name="Reply Dress", sizes=[], colors=[], links=[]),
        )
        record_sent_product_message(
            session,
            tenant_id="tenant-reply",
            conversation_id="conv-r",
            channel="instagram_dm",
            sent_message_id="msg-123",
            product_id=product["id"],
        )
        resolved = resolve_reply_to_product(
            session,
            tenant_id="tenant-reply",
            channel="instagram_dm",
            reply_to_message_id="msg-123",
        )
        assert resolved == product["id"]


def test_xlsx_template_and_preview(products_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers = _auth_headers("tenant-xlsx")
    template = client.get("/api/mobile/products/import/template.xlsx", headers=headers)
    assert template.status_code == 200
    rows = parse_xlsx_bytes(template.content)
    assert any(row.get("name") == "Rose Lipstick" for row in rows)
    encoded = base64.b64encode(template.content).decode("ascii")
    preview = client.post(
        "/api/mobile/products/import/xlsx/preview",
        headers=headers,
        json={"file_base64": encoded},
    )
    assert preview.status_code == 200
    assert preview.json()["valid_count"] >= 1


def test_hard_delete_clears_context_and_reply(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        product = svc.create_product(
            tenant_id="tenant-del",
            body=ProductWriteBody(name="Delete Me", sizes=[], colors=[], links=[]),
        )
        set_active_product(
            session,
            tenant_id="tenant-del",
            conversation_id="conv-del",
            product_id=product["id"],
            source="image_match",
        )
        record_sent_product_message(
            session,
            tenant_id="tenant-del",
            conversation_id="conv-del",
            channel="web_chat",
            sent_message_id="msg-del",
            product_id=product["id"],
        )
        svc.delete_product(tenant_id="tenant-del", product_id=product["id"])
        assert get_active_product(session, tenant_id="tenant-del", conversation_id="conv-del") is None
        assert (
            resolve_reply_to_product(
                session,
                tenant_id="tenant-del",
                channel="web_chat",
                reply_to_message_id="msg-del",
            )
            is None
        )


def test_crv2_active_context_tool(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        product = svc.create_product(
            tenant_id="tenant-tool-ctx",
            body=ProductWriteBody(name="Tool Context Hat", sizes=[], colors=[], links=[]),
        )
        set_active_product(
            session,
            tenant_id="tenant-tool-ctx",
            conversation_id="conv-tool",
            product_id=product["id"],
            source="url_match",
        )
    ctx = ToolContext(
        tenant_id="tenant-tool-ctx",
        published_revision="rev",
        channel="instagram_dm",
        conversation_id="conv-tool",
    )
    out = dispatch_retrieval_tool("get_active_product_context", {}, ctx)
    assert out["ok"] is True
    assert out["data"]["product"]["name"] == "Tool Context Hat"


def test_image_fingerprint_helpers() -> None:
    content = b"test-image-bytes"
    assert sha256_hex(content) == sha256_hex(content)
    assert len(compute_average_phash(content)) == 16
