"""Product image match: exact sha256 + tenant-scoped ANN. Old SCAN_CAP path is gone."""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, select

from db.models import Base
from db.models.products import Product, ProductImageFingerprint
from db.session import reset_engine_for_tests, whatsapp_session
from services.products.image_ann import backfill_missing_ann
from services.products.image_index import find_image_candidates, upsert_product_image_index
from services.products.image_phash_vec import phash_to_vec
from services.products.media import store_product_media
from services.products.schemas import ProductWriteBody
from services.products.service import ProductsService

ROOT = Path(__file__).resolve().parents[1]
LIVE_MATCH = (
    "services/products/image_index.py",
    "services/products/image_ann.py",
    "services/products/image_match.py",
    "services/brain/media/product_image_match.py",
)


@pytest.fixture()
def products_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DASHBOARD_AUTH_SECRET", "ci-dashboard-secret")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DISABLE_API_DOCS", "true")
    monkeypatch.setenv("LINASBOT_DATA_ROOT", str(tmp_path / "data"))
    url = f"sqlite:///{tmp_path / 'products_ann.db'}"
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


def _jpeg(tag: bytes) -> bytes:
    return b"\xff\xd8\xff\xd9" + tag


def test_live_image_path_has_no_scan_cap_or_prefix_like() -> None:
    banned = (
        "LINAS_PRODUCT_IMAGE_SCAN_CAP",
        "SCAN_CAP",
        "PHASH_PREFIX",
        "phash.like",
        "_scan_cap",
        "_phash_prefix",
    )
    hits: list[str] = []
    for rel in LIVE_MATCH:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for token in banned:
            if token in text:
                hits.append(f"{rel}:{token}")
    assert not hits, hits
    ann = (ROOT / "services/products/image_ann.py").read_text(encoding="utf-8")
    assert "tenant_id = :tenant_id" in ann
    assert "phash_embedding <=> CAST(:embedding AS vector)" in ann
    readme = (ROOT / "services/products/README.md").read_text(encoding="utf-8")
    assert "LINAS_PRODUCT_IMAGE_SCAN_CAP" not in readme
    assert "prefix LIKE" in readme or "ANN" in readme


def test_exact_sha256_wins_and_save_writes_ann(products_env: Path) -> None:
    del products_env
    content = _jpeg(b"exact-ann")
    stored = store_product_media(
        tenant_id="t-ann",
        user_id="u1",
        filename="bag.jpg",
        content=content,
        content_type="image/jpeg",
    )
    with whatsapp_session(require=True) as session:
        svc = ProductsService(session)
        created = svc.create_product(
            tenant_id="t-ann",
            body=ProductWriteBody(
                description="brown tote",
                name="Leather Bag",
                sizes=[],
                colors=[],
                images=[{"media_id": stored["media_id"], "sort_order": 0}],
                links=[],
            ),
        )
        row = session.execute(select(ProductImageFingerprint)).scalar_one()
        assert isinstance(row.phash_vec, list)
        assert len(row.phash_vec) == 64
        hits = find_image_candidates(session, tenant_id="t-ann", query_bytes=content, top_k=8)
        assert hits[0]["product_id"] == created["id"]
        assert hits[0]["similarity"] == 1.0
        svc.delete_product(tenant_id="t-ann", product_id=created["id"])
        left = list(session.execute(select(ProductImageFingerprint)).scalars().all())
        assert left == []


def test_ann_is_tenant_scoped(products_env: Path) -> None:
    del products_env
    vec_a = [1.0] * 32 + [0.0] * 32
    vec_b = [0.0] * 32 + [1.0] * 32
    with whatsapp_session(require=True) as session:
        for tid, vec, pid in (("ten-a", vec_a, "pa"), ("ten-b", vec_b, "pb")):
            session.add(
                Product(
                    id=pid,
                    tenant_id=tid,
                    name="X",
                    name_normalized="x",
                    availability="in_stock",
                )
            )
            session.flush()
            upsert_product_image_index(
                session,
                tenant_id=tid,
                product_id=pid,
                product_image_id=f"img-{pid}",
                media_id=f"m-{pid}",
                fingerprint={"sha256": f"sha-{pid}", "phash": "ffff0000ffff0000"},
                histogram=[0.1] * 48,
            )
            row = session.execute(
                select(ProductImageFingerprint).where(ProductImageFingerprint.tenant_id == tid)
            ).scalar_one()
            row.phash_vec = vec
            session.flush()
        from services.products.image_ann import ann_candidate_rows

        hits = ann_candidate_rows(session, tenant_id="ten-a", query_vec=vec_a, fetch=8)
        assert hits
        assert all(row.tenant_id == "ten-a" for row in hits)
        assert all(row.product_id != "pb" for row in hits)


def test_ann_returns_bounded_topk(products_env: Path) -> None:
    del products_env
    query = _jpeg(b"q-top")
    with whatsapp_session(require=True) as session:
        session.add(Product(id="p-root", tenant_id="t-k", name="X", name_normalized="x", availability="in_stock"))
        session.flush()
        for i in range(12):
            upsert_product_image_index(
                session,
                tenant_id="t-k",
                product_id="p-root",
                product_image_id=f"img-{i}",
                media_id=f"m-{i}",
                fingerprint={"sha256": f"{i:064x}", "phash": "aaaaaaaaaaaaaaaa"},
                histogram=[0.2] * 48,
            )
        hits = find_image_candidates(session, tenant_id="t-k", query_bytes=query, top_k=8, similarity_threshold=0.0)
        assert len(hits) <= 8


def test_backfill_writes_missing_vec(products_env: Path) -> None:
    del products_env
    with whatsapp_session(require=True) as session:
        session.add(Product(id="p-bf", tenant_id="t-bf", name="X", name_normalized="x", availability="in_stock"))
        session.flush()
        row = ProductImageFingerprint(
            id="fp-bf",
            tenant_id="t-bf",
            product_id="p-bf",
            product_image_id="img-bf",
            media_id="m-bf",
            sha256="a" * 64,
            phash="abcdabcdabcdabcd",
            histogram=[],
        )
        session.add(row)
        session.flush()
        assert row.phash_vec is None
        out = backfill_missing_ann(session, tenant_id="t-bf", limit=10)
        assert out["updated"] == 1
        session.refresh(row)
        assert row.phash_vec == phash_to_vec("abcdabcdabcdabcd")
        again = backfill_missing_ann(session, tenant_id="t-bf", limit=10)
        assert again["updated"] == 0
