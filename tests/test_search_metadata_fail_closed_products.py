"""Product create/update must not go live without ready English search metadata."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

from db.models import Base
from db.session import reset_engine_for_tests, whatsapp_session
from services.products.schemas import ProductWriteBody
from services.products.search import search_product_by_title
from services.products.service import ProductsError, ProductsService
from services.search_metadata.generate import SearchMetadata, reset_metadata_generator, set_metadata_generator


@pytest.fixture()
def products_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'products_meta.db'}"
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


def _ok() -> None:
    set_metadata_generator(
        lambda req: SearchMetadata(
            title="Named catalog product",
            description="Owner-described catalog product for search.",
            keywords=["catalog"],
        )
    )


def _fail() -> None:
    reset_metadata_generator()
    set_metadata_generator(lambda _req: SearchMetadata())


def _body(**kwargs) -> ProductWriteBody:
    fields = {
        "name": "Nivea Soft",
        "description": "Face moisturizing cream",
        "price": "10",
        "sizes": [],
        "colors": [],
        "note": None,
        "images": [],
        "links": [],
    }
    fields.update(kwargs)
    return ProductWriteBody(**fields)


def setup_function() -> None:
    _ok()


def teardown_function() -> None:
    reset_metadata_generator()


def test_new_product_success_is_searchable(products_db: Path) -> None:
    with whatsapp_session() as session:
        created = ProductsService(session).create_product(tenant_id="t_p_ok", body=_body())
        assert created["ai_search_title"]
        assert created["ai_search_description"]
        product_id = created["id"]
    with whatsapp_session() as session:
        hit_rows = search_product_by_title(session, tenant_id="t_p_ok", title="nivea cream")
        assert hit_rows
        assert hit_rows[0]["id"] == product_id


def test_new_product_metadata_fail_is_not_created(products_db: Path) -> None:
    _fail()
    with pytest.raises(ProductsError) as exc:
        with whatsapp_session() as session:
            ProductsService(session).create_product(tenant_id="t_p_fail", body=_body())
    assert exc.value.code == "METADATA_PREPARATION_FAILED"
    assert exc.value.http_status == 422
    assert "luna" not in exc.value.message.lower()
    with whatsapp_session() as session:
        listed = ProductsService(session).list_products(tenant_id="t_p_fail")
        assert listed["total"] == 0


def test_existing_product_metadata_fail_keeps_old(products_db: Path) -> None:
    with whatsapp_session() as session:
        created = ProductsService(session).create_product(
            tenant_id="t_p_upd",
            body=_body(name="Old Cream", description="Old owner description"),
        )
        product_id = created["id"]
        old_title = created["ai_search_title"]
    _fail()
    with pytest.raises(ProductsError):
        with whatsapp_session() as session:
            ProductsService(session).update_product(
                tenant_id="t_p_upd",
                product_id=product_id,
                body=_body(name="New Cream Name", description="New owner description"),
            )
    with whatsapp_session() as session:
        row = ProductsService(session).get_product(tenant_id="t_p_upd", product_id=product_id)
        assert row["name"] == "Old Cream"
        assert row["description"] == "Old owner description"
        assert row["ai_search_title"] == old_title


def test_description_still_required(products_db: Path) -> None:
    with pytest.raises(ProductsError) as exc:
        with whatsapp_session() as session:
            ProductsService(session).create_product(
                tenant_id="t_p_desc",
                body=_body(description=""),
            )
    assert exc.value.code == "DESCRIPTION_REQUIRED"


def test_weak_description_does_not_invent_and_keeps_empty_keywords(products_db: Path) -> None:
    set_metadata_generator(
        lambda _req: SearchMetadata(
            title="Nivea Face Cream",
            description="Face cream for dry skin after laser.",
            keywords=["face", "laser"],
        )
    )
    with whatsapp_session() as session:
        created = ProductsService(session).create_product(
            tenant_id="t_p_weak",
            body=_body(name="Nivea", description="aaa"),
        )
    blob = f"{created['ai_search_title']} {created['ai_search_description']}".lower()
    assert "face cream" not in blob
    assert "laser" not in blob
    assert created["ai_search_title"]
    assert created["ai_search_description"]
    assert created.get("ai_search_keywords") in (None, [], [])
