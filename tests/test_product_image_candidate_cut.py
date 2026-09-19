"""DM image match uses a pHash prefix bucket + hard cap, not a full-table score."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_image_index_buckets_by_phash_prefix_and_caps_scan() -> None:
    from services.products.image_index import PHASH_PREFIX_LEN, _phash_prefix, _scan_cap

    src = (ROOT / "services/products/image_index.py").read_text(encoding="utf-8")
    assert "phash.like" in src
    assert "SCAN_CAP" in src
    assert "sha256 ==" in src or "sha256==" in src
    assert _phash_prefix("abcd1234") == "ab"
    assert PHASH_PREFIX_LEN == 2
    assert _scan_cap() >= 32
    model = (ROOT / "db/models/products.py").read_text(encoding="utf-8")
    assert "ix_product_img_fp_tenant_phash" in model
    alembic = (ROOT / "alembic/versions/20260919_prod_img_phash_prefix.py").read_text(encoding="utf-8")
    assert "ix_product_img_fp_tenant_phash" in alembic
    readme = (ROOT / "services/products/README.md").read_text(encoding="utf-8")
    assert "**not** million-row HNSW" in readme
    assert "LINAS_PRODUCT_IMAGE_SCAN_CAP" in readme
