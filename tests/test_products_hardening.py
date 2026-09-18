"""AI Products final hardening — image index HA, priority, reply-to."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event

os.environ["LINAS_WHATSAPP_ALLOW_SQLITE"] = "true"

from db.models import Base  # noqa: E402
from db.session import reset_engine_for_tests, whatsapp_session  # noqa: E402
from services.products.image_fingerprint import (  # noqa: E402
    combined_image_similarity,
    compute_color_histogram,
    compute_fingerprint,
)
from services.products.image_index import find_image_candidates  # noqa: E402
from services.products.media import store_product_media  # noqa: E402
from services.products.outbound_hook import (  # noqa: E402
    maybe_record_product_outbound,
    record_product_outbound_direct,
    set_pending_product_outbound,
)
from services.products.reply_to_map import resolve_reply_to_product  # noqa: E402
from services.products.repository import ProductsRepository  # noqa: E402
from services.products.schemas import ProductWriteBody  # noqa: E402
from services.products.service import ProductsService  # noqa: E402


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'products_hardening.db'}"
    monkeypatch.setenv("LINAS_WHATSAPP_DATABASE_URL", url)
    monkeypatch.setenv("LINAS_WHATSAPP_ALLOW_SQLITE", "true")
    reset_engine_for_tests()
    engine = create_engine(url, future=True)

    @event.listens_for(engine, "connect")
    def _fk(dbapi_conn, _connection_record):  # type: ignore[no-untyped-def]
        dbapi_conn.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    import main  # noqa: F401

    yield tmp_path
    reset_engine_for_tests()


def test_color_secondary_to_phash(products_env: Path) -> None:
    """Same structure different color should score higher via pHash than histogram alone."""
    base = b"\xff\xd8\xff\xe0" + b"\x00" * 200
    variant = b"\xff\xd8\xff\xe0" + b"\xff" * 200
    fp_base = compute_fingerprint(base)
    fp_var = compute_fingerprint(variant)
    hist_base = compute_color_histogram(base)
    hist_var = compute_color_histogram(variant)
    entry = {"sha256": fp_base["sha256"], "phash": fp_base["phash"], "histogram": hist_base}
    sim_same = combined_image_similarity(query_fp=fp_base, query_hist=hist_base, entry=entry)
    sim_color = combined_image_similarity(query_fp=fp_var, query_hist=hist_var, entry=entry)
    assert sim_same >= 0.99
    assert sim_color > 0.5


def test_two_node_image_index_shared_db(products_env: Path) -> None:
    """Node1 indexes via DB; node2 reads same fingerprints without local JSON."""
    content = b"\xff\xd8\xff\xd9node1"
    stored = store_product_media(
        tenant_id="tenant-ha",
        user_id="u1",
        filename="bag.jpg",
        content=content,
        content_type="image/jpeg",
    )
    media_id = str(stored["media_id"])

    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-ha",
            body=ProductWriteBody(
                description="test product",
                name="HA Bag",
                sizes=[],
                colors=[],
                images=[{"media_id": media_id, "sort_order": 0}],
                links=[],
            ),
        )
        session.commit()

    with whatsapp_session(require=True) as session_node2:
        hits = find_image_candidates(session_node2, tenant_id="tenant-ha", query_bytes=content, top_k=8)
    assert len(hits) >= 1
    assert hits[0]["product_id"]


def test_inactive_excluded_from_customer_candidates(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-luna-inactive",
            body=ProductWriteBody(
                description="test product", name="Hidden Item", availability="inactive", sizes=[], colors=[], links=[]
            ),
        )
        svc.create_product(
            tenant_id="tenant-luna-inactive",
            body=ProductWriteBody(
                description="test product", name="Visible Item", availability="in_stock", sizes=[], colors=[], links=[]
            ),
        )
        from services.products.repository import ProductsRepository

        rows = ProductsRepository(session).list_all_for_tenant(tenant_id="tenant-luna-inactive", customer_facing=True)
        names = {row.name for row in rows}
    assert "Hidden Item" not in names
    assert "Visible Item" in names


def test_reply_to_outbound_end_to_end(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        product = svc.create_product(
            tenant_id="tenant-outbound",
            body=ProductWriteBody(description="test product", name="Outbound Dress", sizes=[], colors=[], links=[]),
        )
        session.commit()
        product_id = product["id"]

    record_product_outbound_direct(
        tenant_id="tenant-outbound",
        conversation_id="conv-out",
        channel="instagram_dm",
        sent_message_id="mid-out-001",
        product_id=product_id,
    )
    with whatsapp_session(require=True) as session:
        resolved = resolve_reply_to_product(
            session,
            tenant_id="tenant-outbound",
            channel="instagram_dm",
            reply_to_message_id="mid-out-001",
        )
    assert resolved == product_id

    user_data = {
        "tenant_id": "tenant-outbound",
        "conversation_id": "conv-hook",
        "channel": "web_chat",
    }
    set_pending_product_outbound(user_data, product_id=product_id)
    assert maybe_record_product_outbound(user_data, provider_message_id="mid-hook-002") is True
    with whatsapp_session(require=True) as session:
        assert (
            resolve_reply_to_product(
                session,
                tenant_id="tenant-outbound",
                channel="web_chat",
                reply_to_message_id="mid-hook-002",
            )
            == product_id
        )


def test_out_of_stock_searchable_not_purchasable_hint(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-oos2",
            body=ProductWriteBody(
                description="test product",
                name="Sold Out Hat",
                availability="out_of_stock",
                sizes=[],
                colors=[],
                links=[],
            ),
        )
        matches = ProductsRepository(session).search_by_title_prefix(tenant_id="tenant-oos2", query="hat", limit=3)
        assert matches[0].availability == "out_of_stock"


def test_url_name_conflict_ambiguous(products_env: Path) -> None:
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        svc.create_product(
            tenant_id="tenant-conflict",
            body=ProductWriteBody(
                description="test product",
                name="Alpha Shoe",
                sizes=[],
                colors=[],
                links=[{"url": "https://shop.example.com/alpha", "label": "Buy", "sort_order": 0}],
            ),
        )
        svc.create_product(
            tenant_id="tenant-conflict",
            body=ProductWriteBody(
                description="test product",
                name="Beta Bag",
                sizes=[],
                colors=[],
                links=[{"url": "https://shop.example.com/beta", "label": "Buy", "sort_order": 0}],
            ),
        )
        repo = ProductsRepository(session)
        by_name = repo.search_by_title_prefix(tenant_id="tenant-conflict", query="alpha shoe", limit=5)
        by_url = repo.find_by_link_url(
            tenant_id="tenant-conflict",
            normalized_url="shop.example.com/beta",
        )
        assert by_name and by_name[0].name == "Alpha Shoe"
        assert by_url is not None
        assert by_url.name == "Beta Bag"
        assert by_name[0].id != by_url.id
