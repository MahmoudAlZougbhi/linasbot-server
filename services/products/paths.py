"""Tenant-scoped AI Products filesystem layout."""

from __future__ import annotations

from pathlib import Path

from storage.persistent_storage import get_data_root


def tenant_products_root(tenant_id: str) -> Path:
    tid = str(tenant_id or "").strip()
    if not tid:
        raise ValueError("tenant_id required")
    return Path(get_data_root()) / "tenants" / tid / "products"


def product_media_dir(tenant_id: str) -> Path:
    return tenant_products_root(tenant_id) / "media"
