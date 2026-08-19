"""Similar product names must not pick the wrong SKU with confidence."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from db.models import Base
from db.session import reset_engine_for_tests, whatsapp_session
from services.products.schemas import ProductWriteBody
from services.products.search import search_product_by_title
from services.products.service import ProductsService


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'similar.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    yield tmp_path
    reset_engine_for_tests()


def _seed(tenant_id: str) -> dict[str, str]:
    catalog = [
        ("Nivea Face Cream 50 ml", "Face moisturizing cream 50 millilitres."),
        ("Nivea Face Cream 100 ml", "Face moisturizing cream 100 millilitres."),
        ("Nivea Soft Face Cream", "Light face moisturizing cream."),
        ("Nivea Body Cream", "Body moisturizing cream."),
    ]
    ids: dict[str, str] = {}
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        for name, description in catalog:
            row = svc.create_product(
                tenant_id=tenant_id,
                body=ProductWriteBody(name=name, description=description, sizes=[], colors=[], links=[]),
            )
            ids[name] = row["id"]
    return ids


def test_100ml_query_returns_100ml_product(products_env: Path) -> None:
    ids = _seed("t-sim")
    with whatsapp_session(require=True) as session:
        hits = search_product_by_title(
            session,
            tenant_id="t-sim",
            title="عندكم نيفيا فيس كريم 100 مل؟",
            alternate_queries=["Nivea Face Cream 100 ml"],
            limit=5,
        )
    assert hits
    assert hits[0]["id"] == ids["Nivea Face Cream 100 ml"]
    assert hits[0]["name"] == "Nivea Face Cream 100 ml"


def test_ambiguous_nivea_cream_returns_multiple_not_one_wrong_sku(products_env: Path) -> None:
    ids = _seed("t-sim2")
    with whatsapp_session(require=True) as session:
        original = search_product_by_title(
            session,
            tenant_id="t-sim2",
            title="عندكم نيفيا كريم؟",
            alternate_queries=["Nivea cream", "Nivea Face Cream"],
            limit=5,
        )
    names = [row["name"] for row in original]
    assert len(original) >= 2, names
    assert ids["Nivea Body Cream"] in {row["id"] for row in original} or "Nivea Face Cream" in " ".join(names)
    # Unique auto-context is only applied when match_count == 1 (crv2_tools).
    # Multiple strong hits stay ambiguous so Terra is not handed one wrong SKU.
    assert len(original) != 1 or original[0]["name"] != "Nivea Body Cream"
