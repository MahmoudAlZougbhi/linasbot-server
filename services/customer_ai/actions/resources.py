"""send_resource by authorized ID. Invented URLs never resolve."""

from __future__ import annotations

from typing import Any

from services.cm.setup_resources import resolve_published_resource
from services.customer_ai.contracts.actions import ActionProposal, ActionReceipt
from services.customer_ai.visual import visual_path_for_resource


def looks_like_invented_url(value: str) -> bool:
    text = (value or "").strip().lower()
    return text.startswith("http://") or text.startswith("https://") or "://" in text


def resolve_authorized_resource(
    *,
    tenant_id: str,
    resource_ref: str,
    allowed_source_ids: list[str] | None = None,
    session: Any | None = None,
) -> dict[str, Any]:
    ref = str(resource_ref or "").strip()
    if not ref:
        return {"ok": False, "error": "resource_ref_required"}
    if looks_like_invented_url(ref):
        return {"ok": False, "error": "invented_url"}
    published = resolve_published_resource(
        tenant_id=tenant_id,
        resource_ref=ref,
        allowed_source_ids=allowed_source_ids,
    )
    if published.get("ok"):
        record = dict(published.get("resource") or {})
        record["visual_path"] = visual_path_for_resource(has_authorized_id=True)
        return {"ok": True, "resource": record, "kind": "published"}
    product = _resolve_product_media(session=session, tenant_id=tenant_id, media_id=ref)
    if product is not None:
        return {"ok": True, "resource": product, "kind": "product_media"}
    return {"ok": False, "error": published.get("error") or "resource_not_found"}


def send_resource(
    *,
    tenant_id: str,
    proposal: ActionProposal,
    session: Any | None = None,
) -> ActionReceipt:
    ref = str(proposal.target_id or proposal.fields.get("resource_ref") or "").strip()
    allowed = proposal.fields.get("allowed_source_ids")
    allowed_ids = [str(item) for item in allowed] if isinstance(allowed, list) else None
    resolved = resolve_authorized_resource(
        tenant_id=tenant_id,
        resource_ref=ref,
        allowed_source_ids=allowed_ids,
        session=session,
    )
    if not resolved.get("ok"):
        return ActionReceipt(
            action_id=f"resource:{proposal.task_id}",
            action_type="send_resource",
            state="rejected",
            reason=str(resolved.get("error") or "resource_not_found"),
        )
    resource = dict(resolved.get("resource") or {})
    return ActionReceipt(
        action_id=f"resource:{proposal.task_id}",
        action_type="send_resource",
        state="pending",
        backend_id=str(resource.get("resource_ref") or ref),
        reason="awaiting_delivery",
        idempotency_key=str(proposal.fields.get("idempotency_key") or f"{tenant_id}:{ref}:{proposal.task_id}"),
    )


def _resolve_product_media(*, session: Any | None, tenant_id: str, media_id: str) -> dict[str, Any] | None:
    if session is None or not tenant_id or not media_id:
        return None
    try:
        from sqlalchemy import select

        from db.models.products import Product, ProductImage
        from services.products.availability import is_customer_searchable
    except Exception:
        return None
    stmt = (
        select(ProductImage, Product)
        .join(Product, Product.id == ProductImage.product_id)
        .where(
            ProductImage.tenant_id == tenant_id,
            Product.tenant_id == tenant_id,
            ProductImage.media_id == media_id,
        )
    )
    try:
        row = session.execute(stmt).first()
    except Exception:
        return None
    if row is None:
        return None
    image, product = row
    if not is_customer_searchable(str(getattr(product, "availability", "") or "")):
        return None
    return {
        "resource_ref": media_id,
        "tenant_id": tenant_id,
        "source_type": "product_media",
        "source_item_id": str(getattr(product, "id", "") or ""),
        "resource_type": "image",
        "title": str(getattr(product, "name", "") or media_id),
        "visual_path": visual_path_for_resource(has_authorized_id=True),
    }
