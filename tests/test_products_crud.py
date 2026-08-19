"""AI Products CRUD, tenant isolation, and max-5-images enforcement."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.products.media import store_product_media  # noqa: E402
from services.products.schemas import ProductImageInput, ProductWriteBody  # noqa: E402
from services.products.search import search_product_by_title  # noqa: E402
from services.products.service import ProductsError, ProductsService  # noqa: E402


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'products.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    import modules.mobile_products_api  # noqa: F401
    import modules.products_media_api  # noqa: F401

    yield tmp_path
    reset_engine_for_tests()


def _auth_headers(tenant_id: str) -> dict[str, str]:
    from services.dashboard_session_service import session_service

    session = session_service.create_session(
        user_id="u-products",
        email="products@example.com",
        role="admin",
        permissions=None,
        tenant_id=tenant_id,
    )
    token = session_service.cookie_value_for(session)
    return {"Authorization": f"Bearer {token}"}


def _store_image(tenant_id: str, name: str = "shirt.jpg") -> str:
    content = b"\xff\xd8\xff\xd9"
    result = store_product_media(
        tenant_id=tenant_id,
        user_id="u-products",
        filename=name,
        content=content,
        content_type="image/jpeg",
    )
    assert result["ok"] is True
    return str(result["media_id"])


def test_product_crud_and_max_five_images(products_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers = _auth_headers("tenant-products")

    create = client.post(
        "/api/mobile/products",
        headers=headers,
        json={
            "name": "Laser Hair Removal Package",
            "description": "Laser hair removal package for the body.",
            "price": "299 AED",
            "sizes": ["S", "M"],
            "colors": ["Nude"],
            "note": "6 sessions",
            "images": [],
            "links": [{"url": "https://example.com/pkg", "label": "Details"}],
        },
    )
    assert create.status_code == 200, create.text
    product_id = create.json()["product"]["id"]

    listed = client.get("/api/mobile/products", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    media_ids = [_store_image("tenant-products", f"p{i}.jpg") for i in range(5)]
    update = client.put(
        f"/api/mobile/products/{product_id}",
        headers=headers,
        json={
            "name": "Laser Hair Removal Package",
            "price": "299 AED",
            "sizes": ["S", "M"],
            "colors": ["Nude"],
            "note": "6 sessions",
            "images": [
                {"media_id": media_ids[0], "sort_order": 0},
                {"media_id": media_ids[1], "sort_order": 1},
                {"media_id": media_ids[2], "sort_order": 2},
                {"media_id": media_ids[3], "sort_order": 3},
                {"media_id": media_ids[4], "sort_order": 4},
            ],
            "links": [],
        },
    )
    assert update.status_code == 200, update.text
    assert len(update.json()["product"]["images"]) == 5

    extra = _store_image("tenant-products", "p5.jpg")
    too_many = client.put(
        f"/api/mobile/products/{product_id}",
        headers=headers,
        json={
            "name": "Laser Hair Removal Package",
            "price": "299 AED",
            "sizes": [],
            "colors": [],
            "note": None,
            "images": [
                {"media_id": media_ids[0], "sort_order": 0},
                {"media_id": media_ids[1], "sort_order": 1},
                {"media_id": media_ids[2], "sort_order": 2},
                {"media_id": media_ids[3], "sort_order": 3},
                {"media_id": media_ids[4], "sort_order": 4},
                {"media_id": extra, "sort_order": 5},
            ],
            "links": [],
        },
    )
    assert too_many.status_code == 422

    deleted = client.delete(f"/api/mobile/products/{product_id}", headers=headers)
    assert deleted.status_code == 200
    missing = client.get(f"/api/mobile/products/{product_id}", headers=headers)
    assert missing.status_code == 404


def test_tenant_isolation(products_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers_a = _auth_headers("tenant-a")
    headers_b = _auth_headers("tenant-b")

    created = client.post(
        "/api/mobile/products",
        headers=headers_a,
        json={"name": "Tenant A Serum", "description": "Serum for tenant A", "price": "50", "sizes": [], "colors": [], "links": []},
    )
    assert created.status_code == 200
    product_id = created.json()["product"]["id"]

    cross_get = client.get(f"/api/mobile/products/{product_id}", headers=headers_b)
    assert cross_get.status_code == 404

    cross_delete = client.delete(f"/api/mobile/products/{product_id}", headers=headers_b)
    assert cross_delete.status_code == 404

    still_there = client.get(f"/api/mobile/products/{product_id}", headers=headers_a)
    assert still_there.status_code == 200


def test_create_product_requires_description(products_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers = _auth_headers("tenant-desc")
    missing = client.post(
        "/api/mobile/products",
        headers=headers,
        json={"name": "Nivea", "sizes": [], "colors": [], "links": []},
    )
    assert missing.status_code == 400
    assert missing.json()["detail"]["code"] == "DESCRIPTION_REQUIRED"

    ok = client.post(
        "/api/mobile/products",
        headers=headers,
        json={
            "name": "Nivea Soft",
            "description": "Face moisturizing cream.",
            "sizes": [],
            "colors": [],
            "links": [],
        },
    )
    assert ok.status_code == 200, ok.text
    product = ok.json()["product"]
    assert product["description"] == "Face moisturizing cream."
    assert product["name"] == "Nivea Soft"


def test_csv_import_stub(products_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers = _auth_headers("tenant-import")
    csv_text = "name,price,sizes,colors,note\nVitamin C Serum,120 AED,S|M,Clear,\n"
    imported = client.post(
        "/api/mobile/products/import",
        headers=headers,
        json={"csv_text": csv_text},
    )
    assert imported.status_code == 200, imported.text
    body = imported.json()
    assert body["created"] == 1
    assert body["import_format"] == "csv_v1"


def test_search_product_by_title_fuzzy(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-search",
            body=ProductWriteBody(description="test product", name="Hydrating Face Cream", sizes=[], colors=[], links=[]),
        )
        svc.create_product(
            tenant_id="tenant-search",
            body=ProductWriteBody(description="test product", name="SPF 50 Sunscreen", sizes=[], colors=[], links=[]),
        )
        matches = search_product_by_title(
            session,
            tenant_id="tenant-search",
            title="hydrating cream",
            limit=3,
        )
    assert any(row["name"] == "Hydrating Face Cream" for row in matches)


def test_service_rejects_unknown_media(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        with pytest.raises(ProductsError) as exc:
            svc.create_product(
                tenant_id="tenant-media",
                body=ProductWriteBody(
                    description="test product",
                    name="Bad Image Product",
                    images=[ProductImageInput(media_id="prdim_missing", sort_order=0)],
                    sizes=[],
                    colors=[],
                    links=[],
                ),
            )
    assert exc.value.code == "INVALID_MEDIA"
