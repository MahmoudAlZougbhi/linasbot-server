"""Resolve customer-visible product media/link by id. Hydrate by id only."""

from __future__ import annotations

from typing import Any

from services.products.availability import is_customer_searchable
from services.products.media_descriptors import product_source_item_id


def product_ids_for_inventory(args: dict[str, Any], source_ids: list[str]) -> list[str]:
    ids: list[str] = []
    raw_pid = str(args.get("product_id") or "").strip()
    if raw_pid:
        ids.append(raw_pid.split(":", 1)[1] if raw_pid.startswith("products:") else raw_pid)
    for raw in source_ids:
        sid = str(raw or "").strip()
        if sid.startswith("products:"):
            ids.append(sid.split(":", 1)[1])
    return list(dict.fromkeys(item for item in ids if item))[:32]


def source_allowed(product_id: str, allowed_source_ids: list[str] | None) -> bool:
    wanted = {str(item).strip() for item in (allowed_source_ids or []) if str(item).strip()}
    if not wanted:
        return True
    pid = str(product_id or "").strip()
    sid = product_source_item_id(pid)
    if pid in wanted or sid in wanted:
        return True
    return any(sid.endswith(f":{item}") or item in sid or item in pid for item in wanted)


def resolve_customer_product_resource(
    *,
    tenant_id: str,
    resource_ref: str,
    allowed_source_ids: list[str] | None = None,
    session: Any | None = None,
) -> dict[str, Any] | None:
    tid = str(tenant_id or "").strip()
    ref = str(resource_ref or "").strip()
    if not tid or not ref:
        return None
    if session is not None:
        return _resolve_with_session(session, tenant_id=tid, resource_ref=ref, allowed_source_ids=allowed_source_ids)
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
    except Exception:
        return None
    try:
        with whatsapp_session(require=True) as owned:
            return _resolve_with_session(owned, tenant_id=tid, resource_ref=ref, allowed_source_ids=allowed_source_ids)
    except WhatsAppDatabaseUnavailable:
        return None
    except Exception:
        return None


def list_product_inventory_items(*, tenant_id: str, product_ids: list[str]) -> list[dict[str, str]]:
    from services.products.media_descriptors import inventory_items_from_product

    rows = _load_products(tenant_id, product_ids)
    items: list[dict[str, str]] = []
    for row in rows:
        items.extend(inventory_items_from_product(row))
    return items


def _load_products(tenant_id: str, product_ids: list[str]) -> list[Any]:
    ids = [str(item or "").strip() for item in product_ids if str(item or "").strip()][:32]
    if not tenant_id or not ids:
        return []
    try:
        from db.session import WhatsAppDatabaseUnavailable, whatsapp_session
        from services.products.repository import ProductsRepository
    except Exception:
        return []
    try:
        with whatsapp_session(require=True) as session:
            return ProductsRepository(session).get_products_by_ids(tenant_id=tenant_id, product_ids=ids)
    except WhatsAppDatabaseUnavailable:
        return []
    except Exception:
        return []


def _record(
    *, tenant_id: str, product_id: str, resource_ref: str, kind: str, title: str, url: str = ""
) -> dict[str, Any]:
    return {
        "resource_ref": resource_ref,
        "tenant_id": tenant_id,
        "source_type": "product_media",
        "source_item_id": product_source_item_id(product_id),
        "product_id": product_id,
        "resource_type": kind,
        "title": title or resource_ref,
        "media_id": resource_ref if kind != "link" else "",
        "external_url": url,
    }


def _resolve_with_session(
    session: Any,
    *,
    tenant_id: str,
    resource_ref: str,
    allowed_source_ids: list[str] | None,
) -> dict[str, Any] | None:
    from sqlalchemy import or_, select

    from db.models.products import Product, ProductImage, ProductLink

    image_stmt = (
        select(ProductImage, Product)
        .join(Product, Product.id == ProductImage.product_id)
        .where(
            ProductImage.tenant_id == tenant_id,
            Product.tenant_id == tenant_id,
            ProductImage.media_id == resource_ref,
        )
    )
    row = session.execute(image_stmt).first()
    if row is not None:
        image, product = row
        if not is_customer_searchable(str(getattr(product, "availability", "") or "")):
            return None
        pid = str(getattr(product, "id", "") or "")
        if not source_allowed(pid, allowed_source_ids):
            return None
        return _record(
            tenant_id=tenant_id,
            product_id=pid,
            resource_ref=str(getattr(image, "media_id", "") or resource_ref),
            kind="image",
            title=str(getattr(product, "name", "") or resource_ref),
        )
    link_stmt = (
        select(ProductLink, Product)
        .join(Product, Product.id == ProductLink.product_id)
        .where(
            ProductLink.tenant_id == tenant_id,
            Product.tenant_id == tenant_id,
            or_(ProductLink.id == resource_ref, ProductLink.url == resource_ref),
        )
    )
    row = session.execute(link_stmt).first()
    if row is None:
        return None
    link, product = row
    if not is_customer_searchable(str(getattr(product, "availability", "") or "")):
        return None
    pid = str(getattr(product, "id", "") or "")
    if not source_allowed(pid, allowed_source_ids):
        return None
    url = str(getattr(link, "url", "") or "")
    return _record(
        tenant_id=tenant_id,
        product_id=pid,
        resource_ref=str(getattr(link, "id", "") or resource_ref),
        kind="link",
        title=str(getattr(link, "label", None) or getattr(product, "name", "") or url),
        url=url,
    )
