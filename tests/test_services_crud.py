"""Tenant services CRUD, tenant isolation, and option validation."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.service_catalog.catalog_service import ServiceCatalogError, ServiceCatalogService  # noqa: E402
from services.service_catalog.schemas import ServiceOptionInput, ServiceWriteBody  # noqa: E402
from services.service_catalog.search import search_service_by_name  # noqa: E402


@pytest.fixture()
def services_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'services.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    import modules.mobile_services_api  # noqa: F401

    yield tmp_path
    reset_engine_for_tests()


def _auth_headers(tenant_id: str) -> dict[str, str]:
    from services.dashboard_session_service import session_service

    session = session_service.create_session(
        user_id="u-services",
        email="services@example.com",
        role="admin",
        permissions=None,
        tenant_id=tenant_id,
    )
    token = session_service.cookie_value_for(session)
    return {"Authorization": f"Bearer {token}"}


def test_service_crud_with_options(services_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers = _auth_headers("tenant-services")

    create = client.post(
        "/api/mobile/services",
        headers=headers,
        json={
            "name": "Laser Hair Removal",
            "active": True,
            "options": [
                {
                    "machine_name": "Trio",
                    "body_part": "Arms",
                    "staff_name": "Sara",
                    "price": "70",
                    "currency": "USD",
                    "sort_order": 0,
                },
                {
                    "machine_name": "GentleMax",
                    "body_part": "Full body",
                    "price": "120",
                    "currency": "USD",
                    "sort_order": 1,
                },
            ],
        },
    )
    assert create.status_code == 200, create.text
    body = create.json()["service"]
    service_id = body["id"]
    assert body["name"] == "Laser Hair Removal"
    assert len(body["options"]) == 2
    assert body["options"][0]["machine_name"] == "Trio"
    assert body["price_summary"]

    listed = client.get("/api/mobile/services", headers=headers)
    assert listed.status_code == 200
    assert listed.json()["total"] == 1

    update = client.put(
        f"/api/mobile/services/{service_id}",
        headers=headers,
        json={
            "name": "Laser",
            "active": True,
            "options": [
                {
                    "machine_name": None,
                    "body_part": "Face",
                    "staff_name": None,
                    "price": "50 USD",
                    "currency": "USD",
                    "sort_order": 0,
                },
            ],
        },
    )
    assert update.status_code == 200, update.text
    assert update.json()["service"]["name"] == "Laser"
    assert len(update.json()["service"]["options"]) == 1

    deleted = client.delete(f"/api/mobile/services/{service_id}", headers=headers)
    assert deleted.status_code == 200
    missing = client.get(f"/api/mobile/services/{service_id}", headers=headers)
    assert missing.status_code == 404


def test_tenant_isolation(services_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers_a = _auth_headers("tenant-a")
    headers_b = _auth_headers("tenant-b")

    created = client.post(
        "/api/mobile/services",
        headers=headers_a,
        json={
            "name": "Facial",
            "options": [{"price": "80", "currency": "USD"}],
        },
    )
    assert created.status_code == 200
    service_id = created.json()["service"]["id"]

    cross_get = client.get(f"/api/mobile/services/{service_id}", headers=headers_b)
    assert cross_get.status_code == 404

    cross_delete = client.delete(f"/api/mobile/services/{service_id}", headers=headers_b)
    assert cross_delete.status_code == 404

    still_there = client.get(f"/api/mobile/services/{service_id}", headers=headers_a)
    assert still_there.status_code == 200


def test_option_validation_price_required(services_env: Path) -> None:
    from modules.core import app

    client = TestClient(app)
    headers = _auth_headers("tenant-validate")

    missing_price = client.post(
        "/api/mobile/services",
        headers=headers,
        json={
            "name": "Facial",
            "options": [{"machine_name": "Room A", "price": "  ", "currency": "USD"}],
        },
    )
    assert missing_price.status_code == 422

    no_options = client.post(
        "/api/mobile/services",
        headers=headers,
        json={"name": "Facial", "options": []},
    )
    assert no_options.status_code == 422

    with whatsapp_session(require=True) as session:
        svc = ServiceCatalogService(session)
        with pytest.raises(ServiceCatalogError):
            svc.get_service(tenant_id="tenant-validate", service_id="missing-id")


def test_search_service_by_name(services_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ServiceCatalogService(session)
        svc.create_service(
            tenant_id="tenant-search",
            body=ServiceWriteBody(
                name="Hydrafacial",
                options=[ServiceOptionInput(price="90", currency="USD")],
            ),
        )
        svc.create_service(
            tenant_id="tenant-search",
            body=ServiceWriteBody(
                name="Chemical Peel",
                options=[ServiceOptionInput(price="60", currency="USD")],
            ),
        )
        matches = search_service_by_name(
            session,
            tenant_id="tenant-search",
            name="hydra facial",
            limit=3,
        )
    assert any(row["name"] == "Hydrafacial" for row in matches)
