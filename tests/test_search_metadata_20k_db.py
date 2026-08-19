"""SQLite catalog of 20,000 products — measure search loads, not in-memory-only ranking."""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from db.models import Base
from db.models.products import Product
from db.session import reset_engine_for_tests, whatsapp_session
from services.products.repository import ProductsRepository
from services.products.search import search_product_by_title


@pytest.fixture()
def catalog_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'catalog20k.db'}"
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


def _row(tenant_id: str, *, name: str, description: str, code: str = "") -> Product:
    return Product(
        id=str(uuid.uuid4()),
        tenant_id=tenant_id,
        name=name,
        name_normalized=name.lower(),
        description=description,
        description_normalized=description.lower(),
        price="10",
        sizes=[],
        colors=[],
        note=code,
        availability="in_stock",
        ai_search_title=name,
        ai_search_description=description,
        ai_search_title_normalized=name.lower(),
        ai_search_keywords=["nivea"] if "Nivea" in name else ["catalog"],
    )


def _seed_20000(tenant_id: str) -> dict[str, str]:
    specials = {
        "nivea": _row(
            tenant_id,
            name="Nivea Face Cream",
            description="Moisturizing cream for the face.",
        ),
        "code": _row(tenant_id, name="ABC-200", description="Replacement filter cartridge.", code="ABC-200"),
        "model": _row(
            tenant_id,
            name="WH-9000",
            description="Wireless headset with noise cancellation.",
        ),
        "ml50": _row(tenant_id, name="Nivea Face Cream 50 ml", description="Face cream 50 ml."),
        "ml100": _row(tenant_id, name="Nivea Face Cream 100 ml", description="Face cream 100 ml."),
    }
    rows: list[Product] = list(specials.values())
    for i in range(19995):
        name = f"Catalog {i:05d}"
        rows.append(_row(tenant_id, name=name, description="generic catalog item"))
    with whatsapp_session(require=True) as session:
        session.bulk_save_objects(rows)
        session.commit()
    return {key: row.id for key, row in specials.items()}


def test_search_20000_products_sqlite_loads(catalog_env: Path) -> None:
    ids = _seed_20000("t-20k")
    stats = {"list_all": 0, "rows": 0}
    original = ProductsRepository.list_all_for_tenant

    def _counted(self, **kwargs):  # type: ignore[no-untyped-def]
        rows = original(self, **kwargs)
        stats["list_all"] += 1
        stats["rows"] += len(rows)
        return rows

    ProductsRepository.list_all_for_tenant = _counted  # type: ignore[method-assign]
    try:
        with whatsapp_session(require=True) as session:
            started = time.perf_counter()
            exact = search_product_by_title(session, tenant_id="t-20k", title="Nivea Face Cream", limit=5)
            exact_ms = (time.perf_counter() - started) * 1000
            exact_loads = stats["list_all"]

            started = time.perf_counter()
            typo = search_product_by_title(
                session,
                tenant_id="t-20k",
                title="nevia creem",
                alternate_queries=["Nivea Face Cream"],
                limit=5,
            )
            typo_ms = (time.perf_counter() - started) * 1000
            typo_loads = stats["list_all"] - exact_loads

            started = time.perf_counter()
            code = search_product_by_title(session, tenant_id="t-20k", title="ABC-200", limit=5)
            code_ms = (time.perf_counter() - started) * 1000

            missing = search_product_by_title(session, tenant_id="t-20k", title="zyx-not-a-real-product-999", limit=5)
            similar = search_product_by_title(
                session,
                tenant_id="t-20k",
                title="Nivea Face Cream 100 ml",
                limit=5,
            )
            brand = search_product_by_title(session, tenant_id="t-20k", title="Nivea", limit=5)
            arabizi = search_product_by_title(
                session,
                tenant_id="t-20k",
                title="cream lal wej",
                alternate_queries=["Nivea Face Cream"],
                limit=5,
            )
            model = search_product_by_title(session, tenant_id="t-20k", title="WH-9000", limit=5)
    finally:
        ProductsRepository.list_all_for_tenant = original  # type: ignore[method-assign]

    assert exact and exact[0]["id"] == ids["nivea"]
    assert exact_loads == 0
    assert typo and typo[0]["id"] == ids["nivea"]
    assert code and code[0]["id"] == ids["code"]
    assert missing == []
    assert similar and similar[0]["id"] == ids["ml100"]
    assert any(row["id"] == ids["nivea"] for row in brand) or any("Nivea" in row["name"] for row in brand)
    assert arabizi and arabizi[0]["id"] == ids["nivea"]
    assert model and model[0]["id"] == ids["model"]
    assert stats["list_all"] <= 4
    assert stats["rows"] in {0, 20000, 40000, 60000} or stats["rows"] % 20000 == 0
    assert exact_ms < 5000
    assert typo_ms < 20000
    assert code_ms < 5000
    # One search that misses prefix loads the tenant catalog once (cached per search call).
    assert typo_loads <= 1
